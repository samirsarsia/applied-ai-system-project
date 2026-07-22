# Model Card & Responsible AI Reflection — PawPal+ Care Advisor

This document is the graded reflection on responsible AI design for the
PawPal+ Care Advisor (see `README.md` for the system overview and
`agent.py` for the implementation).

## What are the limitations or biases in your system?

- **Offline planner has a narrow, hand-picked vocabulary.** When no
  `ANTHROPIC_API_KEY` is set, `_run_offline()` in `agent.py` only recognizes
  a handful of keyword patterns ("tired", "busy", "exhausted", "only have",
  "cut", "reduce"). A perfectly reasonable request like "can Mochi skip
  grooming today?" won't match any pattern and silently falls through to a
  generic status report instead of taking the requested action. This is a
  real functional gap, not a stylistic one — a user could reasonably believe
  the system understood them when it didn't act at all.
- **"Lighten the load" always targets low-priority tasks over 15 minutes.**
  That threshold is a guess I hardcoded, not something derived from data or
  the owner's actual preferences. It could systematically deprioritize a
  task that matters a lot to a specific owner just because I tagged it
  "low" priority — the system has no way to learn that "low-priority
  enrichment time" might be the one thing keeping an anxious cat calm.
- **Priority-only fairness, inherited from the base PawPal+ scheduler.**
  `Scheduler.build_plan()` always favors "high" priority tasks first. If an
  owner has two pets and one always gets tagged high-priority tasks (e.g. a
  medically needy dog) while the other's needs are tagged low (e.g. a
  "healthy" cat), the second pet's care could be squeezed out of the budget
  every single day without the owner noticing a pattern — the conflict
  detector flags *time* overlaps, not *systematic neglect* across pets.
- **English-only, informal-register keyword matching.** The offline
  planner's keyword list assumes a specific way of phrasing tiredness or
  busyness in English. It will not generalize to other languages or even to
  more formal phrasing, and I did not test it against non-native-English
  phrasing patterns.
- **No persistence.** Both online and offline modes only ever see the
  in-memory `Owner` object for the current process/session — nothing is
  saved between runs, so the "next occurrence" recurrence logic and any
  agent-driven changes vanish when the app restarts.

## Could your AI be misused, and how would you prevent that?

The most concrete misuse risk is **using the agent as a substitute for
veterinary judgment** — e.g., an owner typing symptoms and treating whatever
the assistant says as medical guidance. I addressed this directly: `agent.py`
maintains a `MEDICAL_RED_FLAGS` keyword list (vomiting, bleeding, seizure,
not breathing, poisoning, etc.) checked by `_safety_check()` *before* any
planning happens, in plain Python — not something I'm trusting the LLM's own
judgment to catch consistently. If triggered, the agent refuses to plan and
returns a fixed redirect to a veterinarian, and this path is exercised by
both `tests/test_agent.py::test_medical_keyword_triggers_safety_redirect` and
`evaluation.py` case 4.

A second, smaller risk: the agent can silently drop tasks (`remove_task`)
based on vague language like "I'm busy." In a household where one person
manages the schedule but multiple people rely on it, an ambiguous request
could remove a task another family member expected to happen, with no
confirmation step. I did not build a confirmation/undo flow for this —
that's a real gap, not something I'm claiming to have solved. The trace
output at least makes every removal visible after the fact, so it's
discoverable, just not preventable in real time.

I did not identify a plausible path to *large-scale* misuse (e.g., spam,
fraud) — the system only ever operates on the local Owner/Pet data it's
given and has no network-facing surface other than the outbound call to the
Anthropic API in live mode.

## What surprised you while testing your AI's reliability?

The clearest surprise was in `evaluation.py` case 2: I expected the
scheduler's existing `detect_conflicts()` to make the 08:00 walk/vet-call
conflict "known" to the agent automatically, but the first version of
`_run_offline()` only called `get_schedule` when no other intent matched —
so a request that *did* match an action intent (like "lighten the load")
would act and then never resurface the still-unresolved conflict. I fixed
this by moving `get_schedule` (and the `_verify_plan()` call) to run
unconditionally at the end of every offline turn, regardless of which
action branch fired — verification isn't something that should be optional
depending on which intent matched. This is exactly the built-in "conflicts
are detected but not resolved" tradeoff from the original PawPal+ build
(documented in `reflection.md`) resurfacing at the agent layer: I had to
consciously decide, again, that flagging a conflict is enough and the agent
should not silently pick a winner between two pets' overlapping tasks.

The second surprise was how much the average confidence score in
`evaluation.py` (0.48) undersells the system at a glance — it's dragged down
by the two guardrail-rejection cases which report `confidence: 0.0` by
design (no planning occurred, so there's nothing to be confident *about*).
Reading a single aggregate number without the per-case breakdown would have
been actively misleading, which is why the harness prints both.

## AI Collaboration

I (the developer) worked with Claude (Claude Code) to build this entire
agent layer in one extended session, on top of an already-complete PawPal+
scheduler from Module 2.

**A helpful suggestion:** When I described the constraint that this
environment has no `ANTHROPIC_API_KEY` and no way for me to generate a live
API transcript, Claude proposed an offline deterministic planner that
executes the *same* tool functions and the *same* verification step as the
live-LLM path, rather than either (a) faking transcripts, or (b) blocking
progress until a key was available. That design is why the whole system —
tests, `main.py` demo, `evaluation.py` — is reproducible right now with zero
API cost, while the live-Claude path is fully implemented and just needs an
environment variable to switch on. I considered this the strongest call
Claude made in the session, because it turned a hard blocker (no API access)
into an explicit, honestly-documented architectural feature (a fallback
mode) instead of a workaround I'd have to explain away later.

**A flawed suggestion:** Claude's first pass at the offline "lighten the
schedule" intent adjusted priority on *every* low-priority task but only
removed tasks over an arbitrary 15-minute threshold from *only the mentioned
pet*. When I ran `main.py` against the actual demo data, the very first
version of this logic did nothing visible for the "Mochi seems tired"
prompt, because Mochi's only low-priority task had already been marked
complete earlier in the same demo script — so the demo silently fell through
to a no-op "here's your schedule" response instead of demonstrating the
agent taking any action. That's a real instance of the AI's suggestion
technically working (no error, no crash) while failing to produce a
demo-worthy result, and I caught it only by actually running the terminal
output and reading it, not by trusting that the logic "looked right" in the
code. The fix was to change which pet the demo message targets (Whiskers,
whose low-priority "Play / enrichment" task was still incomplete) rather
than changing the underlying logic — the agent's behavior was correct, my
test data just didn't exercise it. This mirrors the exact lesson from the
original PawPal+ reflection.md: run it and look, don't just read the code
and assume.
