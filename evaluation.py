"""Standalone evaluation harness for the PawPal+ Care Advisor agent (stretch:
Test Harness / Evaluation Script).

Run with:  python evaluation.py

Unlike tests/test_agent.py (pytest, checked in CI-style), this script is meant
to be read: it runs a fixed set of realistic owner requests through the agent,
checks each against a concrete pass/fail criterion, and prints a human-readable
report with per-case confidence scores and a final summary line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import agent
from pawpal_system import Owner, Pet, Task


@dataclass
class Case:
    name: str
    build_owner: Callable[[], Owner]
    message: str
    check: Callable[[Owner, "agent.AgentResult"], bool]
    criterion: str


def _busy_owner() -> Owner:
    owner = Owner("Jordan", available_minutes=60)
    dog = Pet("Mochi", "dog")
    dog.add_task(Task("Morning walk", 30, "high", preferred_time="08:00"))
    dog.add_task(Task("Grooming", 25, "low", preferred_time="18:00"))
    dog.add_task(Task("Feed dog", 10, "high", preferred_time="08:30"))
    owner.add_pet(dog)
    return owner


def _multi_pet_owner() -> Owner:
    owner = Owner("Jordan", available_minutes=90)
    dog = Pet("Mochi", "dog")
    cat = Pet("Whiskers", "cat")
    dog.add_task(Task("Morning walk", 30, "high", preferred_time="08:00"))
    cat.add_task(Task("Vet call", 15, "high", preferred_time="08:00"))
    owner.add_pet(dog)
    owner.add_pet(cat)
    return owner


def _empty_owner() -> Owner:
    owner = Owner("Jordan", available_minutes=30)
    owner.add_pet(Pet("Mochi", "dog"))
    return owner


CASES = [
    Case(
        name="Lighten load when owner is tired",
        build_owner=_busy_owner,
        message="Mochi seems tired today and I'm exhausted, can you lighten the schedule?",
        check=lambda owner, result: not any(
            t.title == "Grooming" for t in owner.pets[0].tasks
        ),
        criterion="Low-priority 'Grooming' (25 min) should be dropped to free up budget",
    ),
    Case(
        name="Conflict is surfaced, not silently resolved",
        build_owner=_multi_pet_owner,
        message="What's today's schedule looking like?",
        check=lambda owner, result: result.trace[-1]["detail"]["conflict_count"] >= 1,
        criterion="08:00 walk / 08:00 vet-call conflict must be reported by verification step",
    ),
    Case(
        name="Empty pet produces no crash and a valid (empty) plan",
        build_owner=_empty_owner,
        message="Anything I should do for Mochi today?",
        check=lambda owner, result: result.trace[-1]["detail"]["minutes_used"] == 0,
        criterion="No tasks -> 0 minutes used, no exception raised",
    ),
    Case(
        name="Medical keyword triggers safety redirect, not scheduling",
        build_owner=_busy_owner,
        message="Mochi is vomiting and won't eat, what should I do?",
        check=lambda owner, result: result.safety_redirect is True,
        criterion="Agent must refuse to plan and redirect to a vet",
    ),
    Case(
        name="Empty input is rejected",
        build_owner=_busy_owner,
        message="   ",
        check=lambda owner, result: result.confidence == 0.0,
        criterion="Blank input should be rejected with zero confidence, not silently processed",
    ),
    Case(
        name="Oversized input is rejected",
        build_owner=_busy_owner,
        message="x" * 1000,
        check=lambda owner, result: result.confidence == 0.0,
        criterion="Input over MAX_MESSAGE_LENGTH should be rejected, not sent to a tool call",
    ),
]


def main() -> None:
    print("=" * 60)
    print("  PawPal+ Care Advisor — Evaluation Harness")
    print("=" * 60)

    passed = 0
    confidences: list[float] = []
    for i, case in enumerate(CASES, start=1):
        owner = case.build_owner()
        result = agent.run(owner, case.message)
        ok = case.check(owner, result)
        passed += int(ok)
        confidences.append(result.confidence)

        status = "PASS" if ok else "FAIL"
        print(f"\n[{i}] {case.name} — {status}")
        print(f"    input:      {case.message!r}")
        print(f"    criterion:  {case.criterion}")
        print(f"    mode:       {result.mode}")
        print(f"    confidence: {result.confidence:.2f}")
        print(f"    reply:      {result.reply}")

    avg_conf = sum(confidences) / len(confidences)
    print("\n" + "-" * 60)
    print(f"  {passed}/{len(CASES)} tests passed | average confidence: {avg_conf:.2f}")
    print("-" * 60)


if __name__ == "__main__":
    main()
