"""PawPal+ AI Care Advisor — the agentic workflow layer.

This is the required AI feature for the applied-ai-system project: an agent
that takes a natural-language request from a pet owner (e.g. "Mochi seems
tired today, can you lighten the schedule?"), PLANS what to do, ACTS by
calling real tools against the live Owner/Pet/Scheduler objects in
pawpal_system.py, and CHECKS its own work before responding — the
plan-act-verify loop that defines an agentic system.

Two execution modes, selected automatically:

- Live LLM mode: if `google-genai` is installed and GEMINI_API_KEY is set,
  the agent calls Gemini with tool-use (function calling). Gemini decides
  which tools to call and in what order; this module only executes them.
- Offline simulation mode (used when no API key is configured): a
  deterministic, keyword-based planner executes the *same* tools through the
  *same* verification step. This keeps the system fully runnable/testable
  with zero cost and zero network dependency, and is the guardrail path used
  when the live API is unavailable or errors.

Both modes share:
- `TOOLS` / `execute_tool()` — the actual actions available to the agent.
- `_safety_check()` — a guardrail that refuses to let the agent handle
  veterinary/medical requests (it redirects to a vet instead of guessing).
- `_verify_plan()` — a self-check step: after acting, the agent re-reads the
  schedule and confirms it still fits the time budget and reports conflicts,
  instead of just trusting whatever it changed.
- A `trace` list capturing every step (thought / tool call / tool result /
  verification), which is what makes the agent's reasoning inspectable
  instead of a black box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from pawpal_system import Owner, Pet, Scheduler, Task

MAX_STEPS = 5  # guardrail: hard cap on agentic loop iterations (no runaway loops)
MAX_MESSAGE_LENGTH = 500  # guardrail: reject absurdly long input instead of choking the LLM

# Medical/emergency keywords trigger a safety redirect instead of scheduling logic.
# This agent plans pet CARE TASKS; it must never attempt to diagnose symptoms.
MEDICAL_RED_FLAGS = (
    "vomit", "bleeding", "blood", "seizure", "collapse", "won't eat", "wont eat",
    "not breathing", "poison", "limping", "swollen", "diarrhea", "lethargic",
    "won't wake", "wont wake", "choking",
)

TOOLS = [
    {
        "name": "get_schedule",
        "description": "Read the owner's current schedule: the built plan, total minutes used, and any time-conflict warnings.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_time_budget",
        "description": "Change how many minutes the owner has available today.",
        "input_schema": {
            "type": "object",
            "properties": {"minutes": {"type": "integer", "description": "New time budget in minutes."}},
            "required": ["minutes"],
        },
    },
    {
        "name": "adjust_priority",
        "description": "Change the priority of an existing task, e.g. to deprioritize something when the owner is short on time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {"type": "string"},
                "task_title": {"type": "string"},
                "new_priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["pet_name", "task_title", "new_priority"],
        },
    },
    {
        "name": "add_task",
        "description": "Add a new care task for a named pet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {"type": "string"},
                "title": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "preferred_time": {"type": "string", "description": "HH:MM, optional"},
            },
            "required": ["pet_name", "title", "duration_minutes"],
        },
    },
    {
        "name": "remove_task",
        "description": "Remove a task from a named pet by title (e.g. because it no longer applies today).",
        "input_schema": {
            "type": "object",
            "properties": {"pet_name": {"type": "string"}, "task_title": {"type": "string"}},
            "required": ["pet_name", "task_title"],
        },
    },
]


@dataclass
class AgentResult:
    """Everything the caller needs to show a transparent, verifiable answer."""

    reply: str
    trace: list[dict] = field(default_factory=list)
    mode: str = "offline-simulation"
    confidence: float = 0.6
    safety_redirect: bool = False


def _find_pet(owner: Owner, pet_name: str) -> Pet | None:
    for pet in owner.pets:
        if pet.name.lower() == pet_name.lower():
            return pet
    return None


def _find_task(pet: Pet, task_title: str) -> Task | None:
    for task in pet.tasks:
        if task.title.lower() == task_title.lower():
            return task
    return None


def execute_tool(owner: Owner, name: str, args: dict) -> dict:
    """Run one tool against the live Owner/Pet/Scheduler state. Never raises —
    validation failures come back as {"error": ...} so the agent (or the
    offline planner) can report them instead of crashing."""
    scheduler = Scheduler(owner)

    if name == "get_schedule":
        plan = scheduler.build_plan()
        return {
            "plan": plan,
            "total_minutes_used": sum(r["duration_minutes"] for r in plan),
            "time_budget": scheduler.time_budget,
            "conflicts": scheduler.detect_conflicts(),
        }

    if name == "set_time_budget":
        minutes = int(args["minutes"])
        if minutes < 0:
            return {"error": f"minutes cannot be negative, got {minutes}"}
        owner.set_available_time(minutes)
        return {"time_budget": owner.available_minutes}

    if name == "adjust_priority":
        pet = _find_pet(owner, args["pet_name"])
        if pet is None:
            return {"error": f"no pet named {args['pet_name']!r}"}
        task = _find_task(pet, args["task_title"])
        if task is None:
            return {"error": f"no task named {args['task_title']!r} for {pet.name}"}
        old = task.priority
        task.priority = args["new_priority"]
        return {"pet": pet.name, "task": task.title, "old_priority": old, "new_priority": task.priority}

    if name == "add_task":
        pet = _find_pet(owner, args["pet_name"])
        if pet is None:
            return {"error": f"no pet named {args['pet_name']!r}"}
        try:
            task = Task(
                title=args["title"],
                duration_minutes=int(args["duration_minutes"]),
                priority=args.get("priority", "medium"),
                preferred_time=args.get("preferred_time"),
            )
        except ValueError as exc:
            return {"error": str(exc)}
        pet.add_task(task)
        return {"pet": pet.name, "added": task.title}

    if name == "remove_task":
        pet = _find_pet(owner, args["pet_name"])
        if pet is None:
            return {"error": f"no pet named {args['pet_name']!r}"}
        task = _find_task(pet, args["task_title"])
        if task is None:
            return {"error": f"no task named {args['task_title']!r} for {pet.name}"}
        pet.remove_task(task)
        return {"pet": pet.name, "removed": task.title}

    return {"error": f"unknown tool {name!r}"}


def _verify_plan(owner: Owner) -> dict:
    """Self-check step: re-read the schedule after acting and confirm the
    plan still respects the time budget and surface any conflicts, instead of
    assuming the tool calls left things in a good state."""
    scheduler = Scheduler(owner)
    plan = scheduler.build_plan()
    used = sum(r["duration_minutes"] for r in plan)
    conflicts = scheduler.detect_conflicts()
    within_budget = used <= scheduler.time_budget
    return {
        "within_budget": within_budget,
        "minutes_used": used,
        "time_budget": scheduler.time_budget,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


def _safety_check(message: str) -> bool:
    """Return True if the message looks like a medical/emergency question this
    scheduling agent must NOT try to answer."""
    lowered = message.lower()
    return any(flag in lowered for flag in MEDICAL_RED_FLAGS)


def run(owner: Owner, message: str) -> AgentResult:
    """Entry point used by app.py and main.py. Validates input, applies the
    medical-safety guardrail, then dispatches to live-LLM or offline mode."""
    trace: list[dict] = []

    if not message or not message.strip():
        return AgentResult(reply="Please enter a request first.", trace=trace, confidence=0.0)
    if len(message) > MAX_MESSAGE_LENGTH:
        return AgentResult(
            reply=f"That request is too long ({len(message)} chars). Please keep it under {MAX_MESSAGE_LENGTH}.",
            trace=trace,
            confidence=0.0,
        )

    trace.append({"step": "input_validation", "detail": "message length and emptiness OK"})

    if _safety_check(message):
        trace.append({"step": "safety_guardrail", "detail": "medical/emergency keywords detected — refusing to plan, redirecting to a vet"})
        return AgentResult(
            reply=(
                "That sounds like it could be a medical or emergency concern, not a scheduling "
                "question — please contact your veterinarian (or an emergency vet line) directly "
                "rather than relying on this scheduling assistant."
            ),
            trace=trace,
            mode="guardrail",
            confidence=1.0,
            safety_redirect=True,
        )

    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _run_live(owner, message, trace)
        except Exception as exc:  # noqa: BLE001 - any API/SDK failure falls back safely
            trace.append({"step": "live_llm_error", "detail": f"{type(exc).__name__}: {exc}"})
            return _run_offline(owner, message, trace, fallback_reason=str(exc))

    trace.append({"step": "mode_selection", "detail": "no GEMINI_API_KEY set — using offline simulation"})
    return _run_offline(owner, message, trace)


_JSON_TYPE_TO_GEMINI = {
    "object": "OBJECT",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
}


def _to_gemini_schema(schema: dict) -> dict:
    """Convert our Claude-style JSON schema (lowercase types) into the
    upper-cased type schema Gemini's function-calling API expects."""
    converted: dict[str, Any] = {"type": _JSON_TYPE_TO_GEMINI[schema["type"]]}
    if "properties" in schema:
        converted["properties"] = {
            key: _to_gemini_schema(value) for key, value in schema["properties"].items()
        }
    if "required" in schema:
        converted["required"] = schema["required"]
    if "enum" in schema:
        converted["enum"] = schema["enum"]
    if "description" in schema:
        converted["description"] = schema["description"]
    return converted


def _run_live(owner: Owner, message: str, trace: list[dict]) -> AgentResult:
    """Real Gemini tool-use agentic loop. Only reached if GEMINI_API_KEY is set."""
    from google import genai  # imported lazily so the module works with no dependency installed
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    system = (
        "You are the PawPal+ Care Advisor. You help a pet owner adjust today's pet-care "
        "schedule using the tools provided. Always call get_schedule at least once before "
        "and after making changes, so your final answer reflects the real, current state. "
        "Be concise. Never give medical advice."
    )
    gemini_tools = [
        types.Tool(
            function_declarations=[
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": _to_gemini_schema(tool["input_schema"]),
                }
                for tool in TOOLS
            ]
        )
    ]
    config = types.GenerateContentConfig(system_instruction=system, tools=gemini_tools)
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=message)])
    ]

    for step in range(MAX_STEPS):
        response = client.models.generate_content(
            model="gemini-flash-latest", contents=contents, config=config,
        )
        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call is not None]
        trace.append({"step": f"llm_turn_{step}", "stop_reason": candidate.finish_reason.name if candidate.finish_reason else "STOP"})

        if not function_calls:
            final_text = "".join(p.text for p in parts if p.text)
            verification = _verify_plan(owner)
            trace.append({"step": "verification", "detail": verification})
            return AgentResult(reply=final_text, trace=trace, mode="live-llm", confidence=0.9)

        contents.append(candidate.content)
        response_parts = []
        for call in function_calls:
            result = execute_tool(owner, call.name, dict(call.args or {}))
            trace.append({"step": "tool_call", "tool": call.name, "args": dict(call.args or {}), "result": result})
            response_parts.append(
                types.Part(function_response=types.FunctionResponse(name=call.name, response=result))
            )
        contents.append(types.Content(role="user", parts=response_parts))

    trace.append({"step": "max_steps_reached", "detail": f"stopped after {MAX_STEPS} agentic turns"})
    verification = _verify_plan(owner)
    trace.append({"step": "verification", "detail": verification})
    return AgentResult(
        reply="I made several adjustments but ran out of planning steps — here's the current schedule.",
        trace=trace,
        mode="live-llm",
        confidence=0.5,
    )


def _run_offline(owner: Owner, message: str, trace: list[dict], fallback_reason: str | None = None) -> AgentResult:
    """Deterministic keyword-based stand-in for the LLM planner. Executes the
    same real tools and the same verification step, so the agentic loop
    (plan -> act -> verify) is genuinely exercised without any API call."""
    lowered = message.lower()
    if fallback_reason:
        trace.append({"step": "fallback_notice", "detail": f"live LLM unavailable ({fallback_reason}); using offline planner"})

    mentioned_pet = next((p for p in owner.pets if p.name.lower() in lowered), None)
    actions: list[dict] = []

    # --- intent: owner is short on time / tired / busy -> lighten the load ---
    if any(kw in lowered for kw in ("tired", "busy", "short on time", "less time", "lighten", "not feeling well", "exhausted")):
        pets_to_adjust = [mentioned_pet] if mentioned_pet else owner.pets
        for pet in pets_to_adjust:
            for task in pet.tasks:
                if not task.completed and task.priority == "low":
                    result = execute_tool(owner, "adjust_priority", {
                        "pet_name": pet.name, "task_title": task.title, "new_priority": "low",
                    })
                    # low-priority, non-essential tasks over 15 min get dropped to free up budget
                    if task.duration_minutes > 15:
                        result = execute_tool(owner, "remove_task", {"pet_name": pet.name, "task_title": task.title})
                        trace.append({"step": "tool_call", "tool": "remove_task",
                                      "args": {"pet_name": pet.name, "task_title": task.title}, "result": result})
                        actions.append({"pet": pet.name, "action": "dropped low-priority task", "task": task.title})

    # --- intent: reduce the available time budget ---
    elif any(kw in lowered for kw in ("only have", "cut", "reduce time", "reduce budget")):
        scheduler = Scheduler(owner)
        new_budget = max(15, int(scheduler.time_budget * 0.5))
        result = execute_tool(owner, "set_time_budget", {"minutes": new_budget})
        trace.append({"step": "tool_call", "tool": "set_time_budget", "args": {"minutes": new_budget}, "result": result})
        actions.append({"action": "reduced time budget", "new_budget": new_budget})

    # --- default: just report current status (a read-only "how are we doing?" query) ---
    schedule_before = execute_tool(owner, "get_schedule", {})
    trace.append({"step": "tool_call", "tool": "get_schedule", "args": {}, "result": schedule_before})

    verification = _verify_plan(owner)
    trace.append({"step": "verification", "detail": verification})

    if actions:
        summary = "; ".join(
            f"{a['action']} for {a.get('pet', 'all pets')}" + (f" ({a['task']})" if "task" in a else "")
            for a in actions
        )
        reply = f"Done — {summary}. "
    else:
        reply = "Here's the current plan. "

    reply += f"{len(schedule_before['plan'])} task(s) scheduled, using {verification['minutes_used']}/{verification['time_budget']} min."
    if verification["conflicts"]:
        reply += f" Note: {verification['conflict_count']} scheduling conflict(s) still need your attention."

    return AgentResult(
        reply=reply,
        trace=trace,
        mode="offline-simulation" if not fallback_reason else "offline-simulation (live-llm fallback)",
        confidence=0.6 if not actions else 0.7,
    )
