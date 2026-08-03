"""PawPal+ demo script (terminal testing ground).

Run with:  python main.py

This is a temporary sandbox to verify the logic layer works end-to-end before
wiring it into the Streamlit UI. It builds an owner with two pets and several
tasks, then prints a readable "Today's Schedule".
"""

import os

import agent
import storage
from pawpal_system import Owner, Pet, Scheduler, Task


def build_demo_owner() -> Owner:
    """Create a sample owner with two pets and a handful of care tasks."""
    owner = Owner("Jordan", available_minutes=90)

    dog = Pet("Mochi", "dog")
    cat = Pet("Whiskers", "cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    # Tasks are added OUT OF ORDER on purpose, so sort_by_time() has real work
    # to do. (Evening grooming first, morning walk last, etc.)
    dog.add_task(Task("Grooming", 25, "medium", preferred_time="18:00"))
    dog.add_task(Task("Feed dog", 10, "high", preferred_time="08:30"))
    dog.add_task(Task("Morning walk", 30, "high", preferred_time="08:00"))
    cat.add_task(Task("Play / enrichment", 20, "low", preferred_time="17:00"))
    cat.add_task(Task("Feed cat", 5, "high", preferred_time="08:15"))

    # Two tasks deliberately scheduled at the SAME time to trigger a conflict:
    # the dog's walk (08:00, 30 min) already runs until 08:30, and this feeding
    # also wants 08:00 — the scheduler should warn instead of crashing.
    cat.add_task(Task("Vet call", 15, "high", preferred_time="08:00"))

    # Mark one task done so filter_by_status() has something to hide/show.
    dog.tasks[0].mark_complete()  # Grooming already done today

    return owner


def demo_sorting_and_filtering(owner: Owner) -> None:
    """Show the new sort_by_time / filter_by_status / filter_by_pet methods."""
    scheduler = Scheduler(owner)
    all_tasks = owner.all_tasks()

    print("\n" + "=" * 52)
    print("  Sorting & Filtering demo")
    print("=" * 52)

    print("\n  As entered (out of order):")
    for t in all_tasks:
        print(f"    {t.preferred_time}  {t.title}")

    print("\n  sort_by_time() -> chronological:")
    for t in scheduler.sort_by_time(all_tasks):
        print(f"    {t.preferred_time}  {t.title}")

    print("\n  filter_by_status(completed=False) -> still to do:")
    for t in scheduler.filter_by_status(all_tasks, completed=False):
        print(f"    {t.title}")

    print("\n  filter_by_status(completed=True) -> already done:")
    for t in scheduler.filter_by_status(all_tasks, completed=True):
        print(f"    {t.title}")

    print("\n  filter_by_pet('Whiskers') -> just the cat's tasks:")
    for t in scheduler.filter_by_pet("Whiskers"):
        print(f"    {t.title}")
    print("=" * 52)


def print_schedule(owner: Owner) -> None:
    """Print a clean, aligned 'Today's Schedule' for the owner's pets."""
    scheduler = Scheduler(owner, day_start="08:00")
    plan = scheduler.build_plan()

    print("=" * 52)
    print(f"  Today's Schedule for {owner.name}")
    print(f"  Time budget: {scheduler.time_budget} min | starts {scheduler.day_start}")
    print("=" * 52)

    if not plan:
        print("  (No tasks scheduled.)")
        return

    total = 0
    for i, row in enumerate(plan, start=1):
        total += row["duration_minutes"]
        print(
            f"  {i}. {row['start']}–{row['end']}  "
            f"{row['title']} ({row['pet']}) "
            f"[{row['priority']}, {row['duration_minutes']} min]"
        )
        print(f"       ↳ {row['reason']}")

    print("-" * 52)
    print(f"  {len(plan)} tasks scheduled, {total} min total.")

    # Show anything that didn't fit, so the demo makes the budget visible.
    scheduled_titles = {(row["pet"], row["title"]) for row in plan}
    skipped = [
        (pet.name, task.title)
        for pet in owner.pets
        for task in pet.tasks
        if not task.completed and (pet.name, task.title) not in scheduled_titles
    ]
    if skipped:
        print(f"  Skipped (over budget): " + ", ".join(t for _, t in skipped))
    print("=" * 52)


def demo_conflicts(owner: Owner) -> None:
    """Show detect_conflicts() flagging overlapping tasks with a warning."""
    scheduler = Scheduler(owner)
    warnings = scheduler.detect_conflicts()

    print("\n" + "=" * 52)
    print("  Conflict detection demo")
    print("=" * 52)
    if warnings:
        for w in warnings:
            print(f"  {w}")
    else:
        print("  No conflicts detected.")
    print("=" * 52)


def demo_ai_care_advisor(owner: Owner) -> None:
    """Run three natural-language requests through the Care Advisor agent and
    print its plan -> act -> verify trace, plus the final schedule impact."""
    print("\n" + "=" * 52)
    print("  AI Care Advisor demo (agentic workflow)")
    print("=" * 52)

    requests = [
        "Whiskers seems tired today and I'm exhausted, can you lighten the schedule?",
        "Mochi is vomiting and won't eat, what should I do?",
        "What's today's schedule looking like?",
    ]
    for message in requests:
        result = agent.run(owner, message)
        print(f"\n  Owner: {message}")
        print(f"  [mode: {result.mode}, confidence: {result.confidence:.2f}]")
        print(f"  Advisor: {result.reply}")
        print("  Trace:")
        for step in result.trace:
            if step["step"] == "tool_call":
                result_summary = step["result"]
                if step["tool"] == "get_schedule":
                    result_summary = {
                        "tasks_scheduled": len(step["result"]["plan"]),
                        "minutes_used": step["result"]["total_minutes_used"],
                        "conflicts": len(step["result"]["conflicts"]),
                    }
                print(f"    - tool_call: {step['tool']}({step['args']}) -> {result_summary}")
            else:
                print(f"    - {step['step']}: {step.get('detail', '')}")
    print("=" * 52)


def demo_persistence(owner: Owner) -> None:
    """Show storage.save_owner()/load_owner() round-tripping the owner's full
    state to a JSON file, proving data survives a restart (not just session
    memory). Uses a throwaway demo path, not the app's real data/owner.json."""
    demo_path = os.path.join("data", "_main_demo_owner.json")

    print("\n" + "=" * 52)
    print("  Persistence demo (save/load to disk)")
    print("=" * 52)

    storage.save_owner(owner, demo_path)
    print(f"  Saved {owner.name}'s {sum(len(p.tasks) for p in owner.pets)} task(s) "
          f"across {len(owner.pets)} pet(s) to {demo_path}")

    reloaded = storage.load_owner(demo_path)
    print(f"  Reloaded from disk: name={reloaded.name!r}, "
          f"pets={[p.name for p in reloaded.pets]}, "
          f"available_minutes={reloaded.available_minutes}")

    match = (
        reloaded.name == owner.name
        and [p.name for p in reloaded.pets] == [p.name for p in owner.pets]
        and reloaded.available_minutes == owner.available_minutes
    )
    print(f"  Round-trip matches original: {match}")
    os.remove(demo_path)  # clean up the demo file; the real app uses data/owner.json
    print("=" * 52)


def main() -> None:
    owner = build_demo_owner()
    print_schedule(owner)
    demo_sorting_and_filtering(owner)
    demo_conflicts(owner)
    demo_ai_care_advisor(owner)
    demo_persistence(owner)


if __name__ == "__main__":
    main()
