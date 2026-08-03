# PawPal+ Care Advisor — Applied AI System

**Base project:** This system extends **PawPal+** (Module 2 project, repo:
[`ai110-module2show-pawpal-starter`](https://github.com/samirsarsia/ai110-module2show-pawpal-starter)).
The original PawPal+ was a Streamlit app that let a pet owner register pets and
care tasks (walks, feeding, meds, grooming) and generate a priority-aware daily
schedule within a time budget, with sorting, filtering, and conflict-warning
logic in a pure-Python `Scheduler` class. It had no AI/LLM component — it was
rule-based scheduling logic only.

## Title and Summary

**PawPal+ Care Advisor** turns that rule-based scheduler into an **agentic AI
system** with real persistence, not just a classroom demo: an AI "Care
Advisor" that a busy pet owner can talk to in plain English ("Mochi seems
tired today, can you lighten the schedule?") instead of manually editing
tasks. The agent doesn't just chat — it **plans, calls real tools that mutate
the live schedule, and verifies its own work** before replying, and it
refuses to answer questions that need a veterinarian instead of a scheduling
assistant. Every pet, task, and schedule change is saved to disk
(`storage.py`) so closing the app and coming back tomorrow doesn't lose
anything — a requirement for something a pet owner would actually keep using,
not just a one-off demo session. This matters because the whole point of
PawPal+ is reducing the mental load of pet care — an assistant you have to
micromanage through forms, and that forgets everything on restart, defeats
that purpose.

## Architecture Overview

See [`diagrams/architecture.mmd`](diagrams/architecture.mmd) for the full
Mermaid source (renders directly on GitHub, or paste it into the
[Mermaid Live Editor](https://mermaid.live)).

```
Owner (Streamlit UI or terminal) → natural-language request
    → agent.py: input guardrails → safety guardrail (medical redirect)
    → PLAN (live Gemini tool-use, or offline deterministic planner as fallback)
    → ACT (execute_tool calls: add_task / remove_task / adjust_priority / set_time_budget / get_schedule)
    → pawpal_system.py (Owner / Pet / Task / Scheduler — the original logic layer, unchanged)
    → VERIFY (rebuild the schedule, confirm it fits the time budget, surface conflicts)
    → reply + full reasoning trace back to the human, who reviews and can override anything
```

The **human-in-the-loop point** is explicit: the agent never hides what it
did. Every response comes with an inspectable trace (in the Streamlit
"Reasoning trace" expander, or printed directly in the terminal demo) so the
owner can see exactly which tool calls were made and what the verification
step found, not just a final answer to trust blindly.

A separate **reliability layer** (`tests/test_agent.py` + `evaluation.py`)
exercises the agent's guardrails and planning logic independently of the UI.

A **persistence layer** (`storage.py`) sits underneath everything: the
Streamlit app loads the last saved `Owner` on startup and re-saves it to
`data/owner.json` after every interaction, so restarting the server (or the
whole machine) doesn't reset the schedule back to the demo defaults.

The original PawPal+ class design is preserved in `diagrams/uml_final.mmd`
(Task / Pet / Owner / Scheduler) — the agent is a new layer on top, not a
rewrite of that logic.

## Required AI Feature: Agentic Workflow

`agent.py` implements a **plan → act → verify** agent loop (`agent.run()`):

1. **Input guardrails** — rejects empty or over-length requests before doing
   anything else.
2. **Safety guardrail** — a fixed list of medical/emergency keywords
   (vomiting, bleeding, seizure, etc.) short-circuits the agent into a refusal
   that redirects the owner to a vet, instead of attempting to "schedule
   around" a medical emergency.
3. **Plan** — decides what to do about the request. Two interchangeable
   planners share everything downstream:
   - **Live mode**: if `GEMINI_API_KEY` is set, Google Gemini is called with
     real [function calling](https://ai.google.dev/gemini-api/docs/function-calling)
     (`agent.TOOLS`, converted to Gemini's schema format) and decides which
     tools to call.
   - **Offline mode** (the default with no key configured): a deterministic
     keyword-based planner that calls the exact same tool functions. This is
     a guardrail path, not a separate feature: any exception from the live
     API (missing package, bad key, network error, rate limit) is caught and
     falls back here automatically, so the system never crashes for lack of
     API access.
4. **Act** — `execute_tool()` runs the chosen tool against the **real, live**
   `Owner`/`Pet`/`Scheduler` objects (the same ones the Streamlit UI reads),
   not a simulated copy. Every tool call is captured in `result.trace`.
5. **Verify** — `_verify_plan()` rebuilds the schedule from scratch after any
   changes and reports whether it's still within budget and whether conflicts
   remain, so the agent checks its own output instead of assuming success.

This satisfies "the feature must meaningfully change how the system behaves":
asking the advisor to "lighten the schedule" actually removes a task from the
owner's real pet — the next time you open the schedule tab, it's changed.

## Setup Instructions

```bash
git clone https://github.com/samirsarsia/applied-ai-system-project.git
cd applied-ai-system-project

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run the interactive app:

```bash
streamlit run app.py
```

Run the terminal demo (scheduler + AI agent, no browser needed):

```bash
python main.py
```

Run the automated tests:

```bash
python -m pytest -v
```

Run the standalone evaluation harness:

```bash
python evaluation.py
```

**To enable live Gemini reasoning** instead of the offline planner, set an API
key (get one free at [Google AI Studio](https://aistudio.google.com/apikey))
before running. The app also auto-loads a `.env` file in the project root via
`python-dotenv`, so you can drop the key in there instead of exporting it each
session:

```bash
echo "GEMINI_API_KEY=your-key-here" > .env
streamlit run app.py   # or: python main.py
```

or export it directly:

```bash
export GEMINI_API_KEY=your-key-here
streamlit run app.py   # or: python main.py
```

Without a key, everything above still runs correctly — the agent uses its
offline fallback, and this is what the sample output below shows.

Your data (owner, pets, tasks) is saved to `data/owner.json` after every
change — it's gitignored, so each clone starts from a clean default owner
rather than someone else's saved pets. Stop the app, run `streamlit run
app.py` again, and everything you entered is still there. Use the "Reset all
data" button in the sidebar to start over.

## Sample Interactions

These are **real captured runs** in this repo (offline-simulation mode — no
`GEMINI_API_KEY` set), taken directly from `python main.py`.

**1. "Lighten the schedule" — the agent actually removes a task**

```
Owner: Whiskers seems tired today and I'm exhausted, can you lighten the schedule?
[mode: offline-simulation, confidence: 0.70]
Advisor: Done — dropped low-priority task for Whiskers (Play / enrichment). 4 task(s) scheduled, using 60/90 min. Note: 1 scheduling conflict(s) still need your attention.
Trace:
  - input_validation: message length and emptiness OK
  - mode_selection: no GEMINI_API_KEY set — using offline simulation
  - tool_call: remove_task({'pet_name': 'Whiskers', 'task_title': 'Play / enrichment'}) -> {'pet': 'Whiskers', 'removed': 'Play / enrichment'}
  - tool_call: get_schedule({}) -> {'tasks_scheduled': 4, 'minutes_used': 60, 'conflicts': 1}
  - verification: {'within_budget': True, 'minutes_used': 60, 'time_budget': 90, 'conflict_count': 1, ...}
```

**2. A medical question is refused, not "scheduled around"**

```
Owner: Mochi is vomiting and won't eat, what should I do?
[mode: guardrail, confidence: 1.00]
Advisor: That sounds like it could be a medical or emergency concern, not a scheduling question — please contact your veterinarian (or an emergency vet line) directly rather than relying on this scheduling assistant.
```

**3. A neutral status query surfaces an unresolved conflict**

```
Owner: What's today's schedule looking like?
[mode: offline-simulation, confidence: 0.60]
Advisor: Here's the current plan. 4 task(s) scheduled, using 60/90 min. Note: 1 scheduling conflict(s) still need your attention.
```

Full raw terminal output (scheduler + sorting/filtering + conflicts + all 3
agent interactions) is reproduced in
[Reproducible Execution Evidence](#reproducible-execution-evidence) below.

### Verified live-LLM run (real Gemini, not simulated)

The offline planner above is the reproducible default with no key configured,
but the live-Gemini tool-use path (`_run_live()` in `agent.py`, using
`gemini-flash-latest` via the `google-genai` SDK) has been manually verified
end-to-end with a real `GEMINI_API_KEY`. This is a real, unedited response
from `python main.py` in live mode:

```
Owner: What's today's schedule looking like?
[mode: live-llm, confidence: 0.90]
Advisor: Here is today's schedule:

**Time Budget:** 90 minutes (60 minutes scheduled)

**Planned Tasks:**
* **08:00 – 08:05:** Feed cat (Whiskers, 5 mins)
* **08:05 – 08:15:** Feed dog (Mochi, 10 mins)
* **08:15 – 08:30:** Vet call (Whiskers, 15 mins)
* **08:30 – 09:00:** Morning walk (Mochi, 30 mins)

*Note:* There is a warning about a potential preferred-time overlap between
Mochi's walk and Whiskers' vet call if scheduled simultaneously at 08:00, but
the current built plan handles them sequentially without overlapping times.
Trace:
  - input_validation: message length and emptiness OK
  - llm_turn_0: (function call: get_schedule)
  - tool_call: get_schedule({}) -> {'tasks_scheduled': 4, 'minutes_used': 60, 'conflicts': 1}
  - llm_turn_1: (final answer)
  - verification: {'within_budget': True, 'minutes_used': 60, 'time_budget': 90, 'conflict_count': 1, ...}
```

Two things stood out from testing this live, both worth being upfront about:

- **Free-tier rate limits are real and low.** The Gemini free tier used here
  caps at 5 requests/minute per model. Running `evaluation.py`'s 6 cases back
  to back tripped `429 RESOURCE_EXHAUSTED` on several cases; the agent's
  existing exception-handling in `run()` caught this exactly as designed and
  fell back to the offline planner (reported in the trace as
  `offline-simulation (live-llm fallback)`), so the app never crashed — it
  just silently downgraded to the deterministic planner mid-run. This is the
  fallback path doing its job, not a bug, but it means a live demo of several
  consecutive requests may show a mix of `live-llm` and
  `offline-simulation (live-llm fallback)` modes depending on how fast you
  send requests.
- **Gemini independently reasoned about a subtlety** in the schedule data:
  asked a neutral status question, it noticed the *reported conflict* (a
  preferred-time overlap between Mochi's walk and Whiskers' vet call) didn't
  actually materialize in the *built plan* (which sequenced them, 08:15–08:30
  then 08:30–09:00) and called that out explicitly instead of just repeating
  the conflict count — correctly identifying the real, pre-existing PawPal+
  tradeoff documented in `reflection.md` §2b (conflict detection uses
  `preferred_time`, but `build_plan()` doesn't honor it). The offline planner
  never notices this; it just reports the conflict count verbatim.

## Design Decisions

- **Offline fallback instead of requiring a live API key.** The agent's
  planner is swappable: live Gemini tool-use when a key is available, a
  deterministic rule-based planner otherwise. I chose this over *requiring*
  an API key so the system is runnable, testable, and gradeable with zero
  cost and zero network dependency, while the architecture for real LLM
  reasoning is fully implemented and just needs an env var to activate. The
  tradeoff is that the offline planner only recognizes a handful of intents
  (see [Limitations](model_card.md) in `model_card.md`) — it's not a general
  language understander.
- **Tools operate on the real Owner/Pet/Scheduler objects, not a sandbox
  copy.** This was a deliberate choice to satisfy "the feature must
  meaningfully change how the system behaves," per the assignment — a demo
  that only *prints* what it would do isn't good enough.
- **A hardcoded safety guardrail lives outside the planner**, so it applies
  identically whether the live LLM or the offline planner is in charge. Model
  behavior (LLM prompting) is not solely trusted for a safety-critical
  refusal — the redirect is checked in Python before any planning happens.
- **Verification is a separate, explicit step**, not folded into "act." This
  mirrors the plan → act → verify pattern from the course material and makes
  the agent's self-check inspectable in the trace, rather than implicit.
- **Kept `pawpal_system.py` untouched.** The agent only calls its existing
  public methods (`add_task`, `set_available_time`, `build_plan`,
  `detect_conflicts`, etc.) — no changes were needed to the original
  Module 2 logic layer, which kept the 24 pre-existing + new tests decoupled
  from the agent work.

Deeper design history from the *original* Module 2 build (class design,
scheduling tradeoffs) is preserved in [`reflection.md`](reflection.md).

## Testing Summary

**Automated tests:** `python -m pytest -v` → **29/29 passed** (12 pre-existing
scheduler tests in `tests/test_pawpal.py`, 12 tests in `tests/test_agent.py`
covering input guardrails, the safety redirect, each tool function including
its error paths, and the offline planner's plan-act-verify behavior, plus 5
tests in `tests/test_storage.py` covering the JSON persistence round-trip).

**Evaluation harness** (`python evaluation.py`, stretch feature — see
[Reproducible Execution Evidence](#reproducible-execution-evidence)):
**6/6 scenario checks passed**, average confidence **0.48** across cases
(pulled down deliberately by the two guardrail-rejection cases, which report
confidence `0.00` by design since no planning occurred).

What worked: the guardrails (empty/oversized input, medical-keyword redirect)
are 100% reliable because they're plain Python checks, not model output. The
verification step correctly reports the Mochi/Whiskers 08:00 time conflict in
every run where it's present.

What didn't: the offline planner is intent-limited — phrasing a request in a
way that doesn't match its keyword list (e.g. "can we skip grooming today?")
falls through to the default status-report behavior instead of taking
action. This is a known, documented limitation of the offline fallback, not
of the agent architecture — live Gemini tool-use mode (once a key is set)
does not have this limitation, since Gemini parses free-form intent itself.

Human evaluation was done by manually running each of the 3 sample
interactions above and confirming the resulting task list and reply matched
the intended behavior.

## Reflection

See [`model_card.md`](model_card.md) for the graded responsible-AI reflection
(limitations/biases, misuse potential, testing surprises, AI collaboration
examples) — required to be there, not here, per the assignment.

## Reproducible Execution Evidence

### `python main.py` (scheduler demo + AI Care Advisor demo, offline mode)

```
====================================================
  Today's Schedule for Jordan
  Time budget: 90 min | starts 08:00
====================================================
  1. 08:00–08:05  Feed cat (Whiskers) [high, 5 min]
       ↳ high-priority task; fit within the remaining 90 min of budget
  2. 08:05–08:15  Feed dog (Mochi) [high, 10 min]
       ↳ high-priority task; fit within the remaining 85 min of budget
  3. 08:15–08:30  Vet call (Whiskers) [high, 15 min]
       ↳ high-priority task; fit within the remaining 75 min of budget
  4. 08:30–09:00  Morning walk (Mochi) [high, 30 min]
       ↳ high-priority task; fit within the remaining 60 min of budget
  5. 09:00–09:20  Play / enrichment (Whiskers) [low, 20 min]
       ↳ low-priority task; fit within the remaining 30 min of budget
----------------------------------------------------
  5 tasks scheduled, 80 min total.
====================================================

====================================================
  Sorting & Filtering demo
====================================================

  As entered (out of order):
    18:00  Grooming
    08:30  Feed dog
    08:00  Morning walk
    17:00  Play / enrichment
    08:15  Feed cat
    08:00  Vet call

  sort_by_time() -> chronological:
    08:00  Morning walk
    08:00  Vet call
    08:15  Feed cat
    08:30  Feed dog
    17:00  Play / enrichment
    18:00  Grooming

  filter_by_status(completed=False) -> still to do:
    Feed dog
    Morning walk
    Play / enrichment
    Feed cat
    Vet call

  filter_by_status(completed=True) -> already done:
    Grooming

  filter_by_pet('Whiskers') -> just the cat's tasks:
    Play / enrichment
    Feed cat
    Vet call
====================================================

====================================================
  Conflict detection demo
====================================================
  ⚠️ Conflict (different pets): 'Morning walk' (Mochi, 08:00–08:30) overlaps 'Vet call' (Whiskers, starts 08:00).
====================================================

====================================================
  AI Care Advisor demo (agentic workflow)
====================================================

  Owner: Whiskers seems tired today and I'm exhausted, can you lighten the schedule?
  [mode: offline-simulation, confidence: 0.70]
  Advisor: Done — dropped low-priority task for Whiskers (Play / enrichment). 4 task(s) scheduled, using 60/90 min. Note: 1 scheduling conflict(s) still need your attention.
  Trace:
    - input_validation: message length and emptiness OK
    - mode_selection: no GEMINI_API_KEY set — using offline simulation
    - tool_call: remove_task({'pet_name': 'Whiskers', 'task_title': 'Play / enrichment'}) -> {'pet': 'Whiskers', 'removed': 'Play / enrichment'}
    - tool_call: get_schedule({}) -> {'tasks_scheduled': 4, 'minutes_used': 60, 'conflicts': 1}
    - verification: {'within_budget': True, 'minutes_used': 60, 'time_budget': 90, 'conflict_count': 1, 'conflicts': ["⚠️ Conflict (different pets): 'Morning walk' (Mochi, 08:00–08:30) overlaps 'Vet call' (Whiskers, starts 08:00)."]}

  Owner: Mochi is vomiting and won't eat, what should I do?
  [mode: guardrail, confidence: 1.00]
  Advisor: That sounds like it could be a medical or emergency concern, not a scheduling question — please contact your veterinarian (or an emergency vet line) directly rather than relying on this scheduling assistant.
  Trace:
    - input_validation: message length and emptiness OK
    - safety_guardrail: medical/emergency keywords detected — refusing to plan, redirecting to a vet

  Owner: What's today's schedule looking like?
  [mode: offline-simulation, confidence: 0.60]
  Advisor: Here's the current plan. 4 task(s) scheduled, using 60/90 min. Note: 1 scheduling conflict(s) still need your attention.
  Trace:
    - input_validation: message length and emptiness OK
    - mode_selection: no GEMINI_API_KEY set — using offline simulation
    - tool_call: get_schedule({}) -> {'tasks_scheduled': 4, 'minutes_used': 60, 'conflicts': 1}
    - verification: {'within_budget': True, 'minutes_used': 60, 'time_budget': 90, 'conflict_count': 1, 'conflicts': ["⚠️ Conflict (different pets): 'Morning walk' (Mochi, 08:00–08:30) overlaps 'Vet call' (Whiskers, starts 08:00)."]}
====================================================

====================================================
  Persistence demo (save/load to disk)
====================================================
  Saved Jordan's 5 task(s) across 2 pet(s) to data/_main_demo_owner.json
  Reloaded from disk: name='Jordan', pets=['Mochi', 'Whiskers'], available_minutes=90
  Round-trip matches original: True
====================================================
```

### `python -m pytest -v` (29/29 passed)

```
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
collected 29 items

tests/test_agent.py::test_empty_message_is_rejected PASSED               [  3%]
tests/test_agent.py::test_oversized_message_is_rejected PASSED           [  6%]
tests/test_agent.py::test_medical_keyword_triggers_safety_redirect PASSED [ 10%]
tests/test_agent.py::test_normal_message_does_not_trigger_safety_redirect PASSED [ 13%]
tests/test_agent.py::test_execute_tool_get_schedule_returns_plan_and_conflicts PASSED [ 17%]
tests/test_agent.py::test_execute_tool_adjust_priority_changes_task PASSED [ 20%]
tests/test_agent.py::test_execute_tool_unknown_pet_returns_error_not_exception PASSED [ 24%]
tests/test_agent.py::test_execute_tool_add_task_validates_via_pawpal_system PASSED [ 27%]
tests/test_agent.py::test_execute_tool_unknown_tool_name_returns_error PASSED [ 31%]
tests/test_agent.py::test_offline_mode_drops_low_priority_task_when_owner_is_tired PASSED [ 34%]
tests/test_agent.py::test_offline_mode_reports_verification_in_trace PASSED [ 37%]
tests/test_agent.py::test_offline_mode_handles_empty_pet_without_crashing PASSED [ 41%]
tests/test_pawpal.py::test_task_completion PASSED                        [ 44%]
tests/test_pawpal.py::test_task_addition_increases_pet_task_count PASSED [ 48%]
tests/test_pawpal.py::test_sort_by_time_returns_chronological_order PASSED [ 51%]
tests/test_pawpal.py::test_sort_by_time_puts_untimed_tasks_last PASSED   [ 55%]
tests/test_pawpal.py::test_daily_task_recurrence_creates_next_day PASSED [ 58%]
tests/test_pawpal.py::test_weekly_task_recurrence_advances_seven_days PASSED [ 62%]
tests/test_pawpal.py::test_once_task_has_no_next_occurrence PASSED       [ 65%]
tests/test_pawpal.py::test_detect_conflicts_flags_overlapping_times PASSED [ 68%]
tests/test_pawpal.py::test_detect_conflicts_none_when_times_do_not_overlap PASSED [ 72%]
tests/test_pawpal.py::test_filter_by_status_splits_done_and_pending PASSED [ 75%]
tests/test_pawpal.py::test_filter_by_pet_returns_only_that_pets_tasks PASSED [ 79%]
tests/test_pawpal.py::test_empty_pet_produces_empty_plan_and_no_conflicts PASSED [ 82%]
tests/test_storage.py::test_save_then_load_round_trips_all_fields PASSED [ 86%]
tests/test_storage.py::test_load_missing_file_returns_none PASSED        [ 89%]
tests/test_storage.py::test_load_corrupt_file_returns_none_not_exception PASSED [ 93%]
tests/test_storage.py::test_save_creates_parent_directories PASSED       [ 96%]
tests/test_storage.py::test_save_overwrites_existing_file PASSED         [100%]

============================== 29 passed in 0.07s ==============================
```

### `python evaluation.py` (reliability/guardrail evaluation harness, 6/6 passed)

```
============================================================
  PawPal+ Care Advisor — Evaluation Harness
============================================================

[1] Lighten load when owner is tired — PASS
    input:      "Mochi seems tired today and I'm exhausted, can you lighten the schedule?"
    criterion:  Low-priority 'Grooming' (25 min) should be dropped to free up budget
    mode:       offline-simulation
    confidence: 0.70
    reply:      Done — dropped low-priority task for Mochi (Grooming). 2 task(s) scheduled, using 40/60 min.

[2] Conflict is surfaced, not silently resolved — PASS
    input:      "What's today's schedule looking like?"
    criterion:  08:00 walk / 08:00 vet-call conflict must be reported by verification step
    mode:       offline-simulation
    confidence: 0.60
    reply:      Here's the current plan. 2 task(s) scheduled, using 45/90 min. Note: 1 scheduling conflict(s) still need your attention.

[3] Empty pet produces no crash and a valid (empty) plan — PASS
    input:      'Anything I should do for Mochi today?'
    criterion:  No tasks -> 0 minutes used, no exception raised
    mode:       offline-simulation
    confidence: 0.60
    reply:      Here's the current plan. 0 task(s) scheduled, using 0/30 min.

[4] Medical keyword triggers safety redirect, not scheduling — PASS
    input:      "Mochi is vomiting and won't eat, what should I do?"
    criterion:  Agent must refuse to plan and redirect to a vet
    mode:       guardrail
    confidence: 1.00
    reply:      That sounds like it could be a medical or emergency concern, not a scheduling question — please contact your veterinarian (or an emergency vet line) directly rather than relying on this scheduling assistant.

[5] Empty input is rejected — PASS
    input:      '   '
    criterion:  Blank input should be rejected with zero confidence, not silently processed
    mode:       offline-simulation
    confidence: 0.00
    reply:      Please enter a request first.

[6] Oversized input is rejected — PASS
    input:      'xxxxxxxxxx...' (1000 chars)
    criterion:  Input over MAX_MESSAGE_LENGTH should be rejected, not sent to a tool call
    mode:       offline-simulation
    confidence: 0.00
    reply:      That request is too long (1000 chars). Please keep it under 500.

------------------------------------------------------------
  6/6 tests passed | average confidence: 0.48
------------------------------------------------------------
```

## Portfolio Reflection

Building the Care Advisor on top of PawPal+ pushed me from "someone who
implements a spec" to someone who has to decide what a spec *should* require
when it's ambiguous — the assignment says "agentic workflow" but doesn't say
whether the demo has to depend on a paid API to be gradeable. Deciding to
build a real, swappable planner (live LLM + honest offline fallback) rather
than either faking a transcript or making the whole submission depend on a
key I might not have at grading time is the kind of tradeoff I expect to keep
making as an AI engineer: reliability and reproducibility are still features,
even on an "AI" project.

- **GitHub:** https://github.com/samirsarsia/applied-ai-system-project
