# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agentic Workflow Enhancement (multi-step reasoning + tool calls)

This project's required AI feature (see `README.md` and `agent.py`) is itself
an agentic workflow, so this section documents the **multi-step reasoning
traces** produced by that agent — the intermediate steps between a natural-
language request and the final reply, captured in `AgentResult.trace`.

### Example trace: "Whiskers seems tired today and I'm exhausted, can you lighten the schedule?"

Captured directly from `python main.py` (offline-simulation mode, no
`ANTHROPIC_API_KEY` set — the same plan → act → verify loop the live-Claude
tool-use path uses):

```
step 1  input_validation   message length and emptiness OK
step 2  mode_selection     no ANTHROPIC_API_KEY set — using offline simulation
step 3  tool_call          remove_task({'pet_name': 'Whiskers', 'task_title': 'Play / enrichment'})
                           -> {'pet': 'Whiskers', 'removed': 'Play / enrichment'}
step 4  tool_call          get_schedule({})
                           -> {'tasks_scheduled': 4, 'minutes_used': 60, 'conflicts': 1}
step 5  verification       {'within_budget': True, 'minutes_used': 60, 'time_budget': 90,
                            'conflict_count': 1,
                            'conflicts': ["⚠️ Conflict (different pets): 'Morning walk' (Mochi,
                            08:00–08:30) overlaps 'Vet call' (Whiskers, starts 08:00)."]}
```

Reasoning behind the steps: the planner recognized "tired"/"exhausted" as a
load-lightening intent, scoped it to the mentioned pet (Whiskers), found her
one low-priority task over the 15-minute drop threshold (`Play /
enrichment`, 20 min), removed it via the real `remove_task` tool (mutating
the live `Owner` object), then — regardless of which action branch fired —
unconditionally re-read the schedule and ran the verification step, which is
what surfaces the still-unresolved Mochi/Whiskers 08:00 conflict in the final
reply. That "always verify, even after an action you're confident about" was
a specific fix during this build — see `model_card.md` for how the first
version of this logic skipped verification when an action intent matched.

### Example trace: "Mochi is vomiting and won't eat, what should I do?"

```
step 1  input_validation   message length and emptiness OK
step 2  safety_guardrail   medical/emergency keywords detected — refusing to plan,
                           redirecting to a vet
```

Only two steps: the safety guardrail short-circuits the plan → act → verify
loop entirely before any tool is even considered, which is intentional — see
`model_card.md` for why this check runs in plain Python rather than being
left to model judgment.

**What I had to verify manually:** I ran `python main.py` and read the raw
trace after every change to `agent.py`, rather than trusting that the logic
"looked right." That's how I caught the ordering bug described in
`model_card.md` (verification being skipped when an action intent matched)
and the demo-data bug where the first `main.py` prompt targeted a pet whose
only low-priority task was already marked complete, producing a misleadingly
inactive demo.

<!-- Prompt Comparison (SF11) not attempted for this project — removed rather than left as an empty template. -->
