"""Tests for the PawPal+ logic layer.

Run with:  python -m pytest

Covers the core behaviors and the higher-risk edge cases:
- basic Task/Pet operations (completion, addition)
- sorting correctness (chronological order)
- recurrence logic (daily/weekly/once)
- conflict detection (overlapping times, and the no-conflict case)
- filtering (by status, by pet)
- empty-pet edge case
"""

from datetime import date, timedelta

from pawpal_system import Owner, Pet, Scheduler, Task


# --- Basic Task / Pet behavior -------------------------------------------


def test_task_completion():
    """Calling mark_complete() should flip the task's status to completed."""
    task = Task("Morning walk", duration_minutes=30, priority="high")

    assert task.completed is False  # starts incomplete

    task.mark_complete()

    assert task.completed is True


def test_task_addition_increases_pet_task_count():
    """Adding a task to a Pet should increase that pet's task count by one."""
    pet = Pet("Mochi", "dog")

    assert len(pet.tasks) == 0  # no tasks yet

    pet.add_task(Task("Feed dog", duration_minutes=10, priority="high"))

    assert len(pet.tasks) == 1


# --- Sorting correctness --------------------------------------------------


def test_sort_by_time_returns_chronological_order():
    """sort_by_time() should return tasks ordered by preferred_time."""
    owner = Owner("Jordan")
    scheduler = Scheduler(owner)

    # Added out of order on purpose.
    tasks = [
        Task("Evening groom", 20, "low", preferred_time="18:00"),
        Task("Morning walk", 30, "high", preferred_time="08:00"),
        Task("Noon meds", 5, "high", preferred_time="12:00"),
    ]

    ordered = scheduler.sort_by_time(tasks)
    times = [t.preferred_time for t in ordered]

    assert times == ["08:00", "12:00", "18:00"]


def test_sort_by_time_puts_untimed_tasks_last():
    """Tasks without a preferred_time should sort to the end."""
    owner = Owner("Jordan")
    scheduler = Scheduler(owner)

    tasks = [
        Task("Anytime play", 15, "low"),  # no preferred_time
        Task("Morning walk", 30, "high", preferred_time="08:00"),
    ]

    ordered = scheduler.sort_by_time(tasks)

    assert ordered[0].title == "Morning walk"
    assert ordered[-1].title == "Anytime play"


# --- Recurrence logic -----------------------------------------------------


def test_daily_task_recurrence_creates_next_day():
    """Completing a daily task should add a new task due the following day."""
    pet = Pet("Mochi", "dog")
    today = date.today()
    walk = Task("Walk", 30, "high", frequency="daily", due_date=today)
    pet.add_task(walk)

    new_task = pet.complete_task(walk)

    # The old one is done; a fresh one exists for tomorrow.
    assert walk.completed is True
    assert new_task is not None
    assert new_task.completed is False
    assert new_task.due_date == today + timedelta(days=1)
    assert len(pet.tasks) == 2  # original (done) + next occurrence


def test_weekly_task_recurrence_advances_seven_days():
    """Completing a weekly task should schedule the next one a week later."""
    pet = Pet("Mochi", "dog")
    today = date.today()
    bath = Task("Bath", 45, "medium", frequency="weekly", due_date=today)
    pet.add_task(bath)

    new_task = pet.complete_task(bath)

    assert new_task is not None
    assert new_task.due_date == today + timedelta(weeks=1)


def test_once_task_has_no_next_occurrence():
    """A one-off task should not spawn a new occurrence when completed."""
    pet = Pet("Mochi", "dog")
    vet = Task("Vet visit", 60, "high", frequency="once")
    pet.add_task(vet)

    new_task = pet.complete_task(vet)

    assert new_task is None
    assert vet.completed is True
    assert len(pet.tasks) == 1  # no new task added


# --- Conflict detection ---------------------------------------------------


def test_detect_conflicts_flags_overlapping_times():
    """Two tasks at the same time should produce a conflict warning."""
    owner = Owner("Jordan")
    pet = Pet("Mochi", "dog")
    owner.add_pet(pet)
    pet.add_task(Task("Walk", 30, "high", preferred_time="08:00"))
    pet.add_task(Task("Feed", 10, "high", preferred_time="08:00"))  # overlaps

    scheduler = Scheduler(owner)
    warnings = scheduler.detect_conflicts()

    assert len(warnings) == 1
    assert "Conflict" in warnings[0]


def test_detect_conflicts_none_when_times_do_not_overlap():
    """Non-overlapping tasks should produce no conflict warnings."""
    owner = Owner("Jordan")
    pet = Pet("Mochi", "dog")
    owner.add_pet(pet)
    pet.add_task(Task("Walk", 30, "high", preferred_time="08:00"))  # 08:00–08:30
    pet.add_task(Task("Feed", 10, "high", preferred_time="09:00"))  # no overlap

    scheduler = Scheduler(owner)

    assert scheduler.detect_conflicts() == []


# --- Filtering ------------------------------------------------------------


def test_filter_by_status_splits_done_and_pending():
    """filter_by_status() should separate completed from pending tasks."""
    owner = Owner("Jordan")
    scheduler = Scheduler(owner)
    done = Task("Groom", 20, "low")
    done.mark_complete()
    pending = Task("Walk", 30, "high")
    tasks = [done, pending]

    assert scheduler.filter_by_status(tasks, completed=True) == [done]
    assert scheduler.filter_by_status(tasks, completed=False) == [pending]


def test_filter_by_pet_returns_only_that_pets_tasks():
    """filter_by_pet() should return just the named pet's tasks."""
    owner = Owner("Jordan")
    dog = Pet("Mochi", "dog")
    cat = Pet("Whiskers", "cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    dog.add_task(Task("Walk", 30, "high"))
    cat.add_task(Task("Play", 15, "low"))

    scheduler = Scheduler(owner)
    cat_tasks = scheduler.filter_by_pet("Whiskers")

    assert len(cat_tasks) == 1
    assert cat_tasks[0].title == "Play"


# --- Edge case: empty pet -------------------------------------------------


def test_empty_pet_produces_empty_plan_and_no_conflicts():
    """A pet with no tasks should yield an empty plan and no conflicts."""
    owner = Owner("Jordan", available_minutes=60)
    owner.add_pet(Pet("Mochi", "dog"))  # no tasks

    scheduler = Scheduler(owner)

    assert scheduler.build_plan() == []
    assert scheduler.detect_conflicts() == []
