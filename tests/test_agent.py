"""Tests for the PawPal+ Care Advisor agent (agent.py).

Run with:  python -m pytest

These run entirely offline (no GEMINI_API_KEY set in CI), which exercises
the deterministic offline planner. That's intentional: it's the same
plan -> act -> verify loop and the same tool functions the live-LLM path
uses, so testing it here is a real test of the agentic machinery, not a
throwaway mock.
"""

from pawpal_system import Owner, Pet, Task

import agent


def _owner_with_tasks() -> Owner:
    owner = Owner("Jordan", available_minutes=60)
    dog = Pet("Mochi", "dog")
    dog.add_task(Task("Morning walk", 30, "high", preferred_time="08:00"))
    dog.add_task(Task("Grooming", 25, "low", preferred_time="18:00"))
    owner.add_pet(dog)
    return owner


# --- input validation guardrails -------------------------------------------


def test_empty_message_is_rejected():
    owner = _owner_with_tasks()
    result = agent.run(owner, "   ")
    assert result.confidence == 0.0
    assert "enter a request" in result.reply.lower()


def test_oversized_message_is_rejected():
    owner = _owner_with_tasks()
    result = agent.run(owner, "x" * (agent.MAX_MESSAGE_LENGTH + 1))
    assert result.confidence == 0.0
    assert "too long" in result.reply.lower()


# --- safety guardrail -------------------------------------------------------


def test_medical_keyword_triggers_safety_redirect():
    owner = _owner_with_tasks()
    result = agent.run(owner, "Mochi is bleeding and won't eat")
    assert result.safety_redirect is True
    assert result.mode == "guardrail"
    assert "vet" in result.reply.lower()


def test_normal_message_does_not_trigger_safety_redirect():
    owner = _owner_with_tasks()
    result = agent.run(owner, "What's today's schedule?")
    assert result.safety_redirect is False


# --- tool execution ----------------------------------------------------------


def test_execute_tool_get_schedule_returns_plan_and_conflicts():
    owner = _owner_with_tasks()
    result = agent.execute_tool(owner, "get_schedule", {})
    assert "plan" in result
    assert "conflicts" in result


def test_execute_tool_adjust_priority_changes_task():
    owner = _owner_with_tasks()
    result = agent.execute_tool(
        owner, "adjust_priority",
        {"pet_name": "Mochi", "task_title": "Grooming", "new_priority": "high"},
    )
    assert result["new_priority"] == "high"
    assert owner.pets[0].tasks[1].priority == "high"


def test_execute_tool_unknown_pet_returns_error_not_exception():
    owner = _owner_with_tasks()
    result = agent.execute_tool(
        owner, "adjust_priority",
        {"pet_name": "NoSuchPet", "task_title": "Grooming", "new_priority": "high"},
    )
    assert "error" in result


def test_execute_tool_add_task_validates_via_pawpal_system():
    owner = _owner_with_tasks()
    result = agent.execute_tool(
        owner, "add_task",
        {"pet_name": "Mochi", "title": "Bath", "duration_minutes": -5},
    )
    assert "error" in result  # Task.__post_init__ rejects non-positive duration


def test_execute_tool_unknown_tool_name_returns_error():
    owner = _owner_with_tasks()
    result = agent.execute_tool(owner, "not_a_real_tool", {})
    assert "error" in result


# --- offline agentic behavior: lighten the load ----------------------------


def test_offline_mode_drops_low_priority_task_when_owner_is_tired():
    owner = _owner_with_tasks()
    result = agent.run(owner, "Mochi seems tired, I'm exhausted, please lighten today's plan")
    assert result.mode == "offline-simulation"
    titles = [t.title for t in owner.pets[0].tasks]
    assert "Grooming" not in titles  # low-priority, >15 min -> dropped
    assert "Morning walk" in titles  # high-priority task is untouched


def test_offline_mode_reports_verification_in_trace():
    owner = _owner_with_tasks()
    result = agent.run(owner, "How's the schedule looking?")
    verification_steps = [s for s in result.trace if s["step"] == "verification"]
    assert len(verification_steps) == 1
    assert "within_budget" in verification_steps[0]["detail"]


def test_offline_mode_handles_empty_pet_without_crashing():
    owner = Owner("Jordan", available_minutes=30)
    owner.add_pet(Pet("Mochi", "dog"))
    result = agent.run(owner, "Anything for Mochi today?")
    assert result.trace[-1]["detail"]["minutes_used"] == 0
