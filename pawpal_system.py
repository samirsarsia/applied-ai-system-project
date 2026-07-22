"""PawPal+ logic layer.

All backend classes for the PawPal+ pet care planning app live here. This is
the "logic layer" that the Streamlit UI (app.py) imports and calls.

Design (see diagrams/uml_draft.mmd):
- Task, Pet, Owner are dataclasses (pure data records).
- Scheduler is a plain class — it is the "brain" that retrieves, organizes, and
  plans tasks across all of an owner's pets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# Single source of truth for how priorities rank when sorting. Higher = more
# important. Both Task.priority_score() and Scheduler.sort_tasks() use this so
# the two never drift apart.
PRIORITY_ORDER: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

# Allowed recurrence values for a task.
VALID_FREQUENCIES = {"daily", "weekly", "once"}


@dataclass
class Task:
    """A single pet care activity (e.g., a morning walk).

    Attributes:
        title: What needs to happen (the description).
        duration_minutes: How long the task takes.
        priority: One of "low", "medium", "high".
        preferred_time: Optional desired clock time, e.g. "08:00".
        frequency: How often it recurs — "daily", "weekly", or "once".
        completed: Whether the task has been done.
        due_date: The date this occurrence is due (defaults to today).
    """

    title: str
    duration_minutes: int
    priority: str = "medium"
    preferred_time: str | None = None
    frequency: str = "daily"
    completed: bool = False
    due_date: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        """Validate priority, frequency, and duration after construction."""
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(
                f"priority must be one of {sorted(PRIORITY_ORDER)}, got {self.priority!r}"
            )
        if self.frequency not in VALID_FREQUENCIES:
            raise ValueError(
                f"frequency must be one of {sorted(VALID_FREQUENCIES)}, got {self.frequency!r}"
            )
        if self.duration_minutes <= 0:
            raise ValueError(f"duration_minutes must be positive, got {self.duration_minutes}")

    def priority_score(self) -> int:
        """Return this task's priority as a number (higher = more important)."""
        return PRIORITY_ORDER[self.priority]

    def fits_within(self, remaining_minutes: int) -> bool:
        """Return True if this task fits in the remaining time budget."""
        return self.duration_minutes <= remaining_minutes

    def mark_done(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def mark_complete(self) -> None:
        """Alias for mark_done(): mark this task as completed."""
        self.mark_done()

    def is_recurring(self) -> bool:
        """Return True if this task repeats (daily or weekly)."""
        return self.frequency in ("daily", "weekly")

    def next_occurrence(self) -> "Task | None":
        """Build the next occurrence of a recurring task, or None if it's one-off.

        The new due date is computed from THIS task's due_date using timedelta,
        so a chain of completions advances accurately (handling month/year and
        leap-year rollovers automatically):
          - daily  -> due_date + 1 day
          - weekly -> due_date + 1 week
          - once   -> no next occurrence (returns None)
        """
        if self.frequency == "daily":
            next_due = self.due_date + timedelta(days=1)
        elif self.frequency == "weekly":
            next_due = self.due_date + timedelta(weeks=1)
        else:  # "once"
            return None

        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            preferred_time=self.preferred_time,
            frequency=self.frequency,
            completed=False,  # the new occurrence starts fresh
            due_date=next_due,
        )


@dataclass
class Pet:
    """An animal that needs care, plus the tasks it needs."""

    name: str
    species: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Attach a care task to this pet."""
        self.tasks.append(task)

    def remove_task(self, task: Task) -> None:
        """Remove a care task from this pet (no-op if it isn't present)."""
        if task in self.tasks:
            self.tasks.remove(task)

    def list_tasks(self) -> list[Task]:
        """Return a copy of this pet's tasks."""
        return list(self.tasks)

    def complete_task(self, task: Task) -> Task | None:
        """Mark a task complete and auto-add its next occurrence if it recurs.

        This is where completion and frequency interact: for a daily/weekly task,
        completing it spawns a fresh instance (via Task.next_occurrence) on the
        next date and appends it to this pet's list. Returns the new occurrence
        (or None for a one-off task).
        """
        task.mark_complete()
        next_task = task.next_occurrence()
        if next_task is not None:
            self.tasks.append(next_task)
        return next_task


@dataclass
class Owner:
    """The person responsible for care. Manages multiple pets."""

    name: str
    available_minutes: int = 0
    preferences: dict = field(default_factory=dict)
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Associate a pet with this owner."""
        self.pets.append(pet)

    def set_available_time(self, minutes: int) -> None:
        """Set/update the daily time budget (minutes)."""
        if minutes < 0:
            raise ValueError(f"available_minutes cannot be negative, got {minutes}")
        self.available_minutes = minutes

    def set_preference(self, key: str, value) -> None:
        """Record a scheduling preference."""
        self.preferences[key] = value

    def all_tasks(self) -> list[Task]:
        """Return every task across all of this owner's pets, tagged with its pet.

        Returns a flat list of (pet, task) is avoided here to keep Task pure; the
        Scheduler pairs pet + task itself via collect_tasks(). This helper just
        flattens the tasks for callers that don't care which pet they belong to.
        """
        tasks: list[Task] = []
        for pet in self.pets:
            tasks.extend(pet.tasks)
        return tasks


class Scheduler:
    """The "brain": retrieves, organizes, and plans tasks across an owner's pets.

    Kept as a plain class (not a dataclass) because it is behavior, not a data
    record. It reads tasks from the Owner's pets, sorts them by priority, greedily
    fits them into the available time budget, and lays them out from day_start.
    """

    def __init__(
        self,
        owner: Owner,
        time_budget: int | None = None,
        day_start: str = "08:00",
    ) -> None:
        """Set up the scheduler with an owner, time budget, and day-start anchor."""
        self.owner = owner
        # Fall back to the owner's available time if no explicit budget is given.
        self.time_budget = time_budget if time_budget is not None else owner.available_minutes
        self.day_start = day_start

    def collect_tasks(self) -> list[tuple[Pet, Task]]:
        """Gather (pet, task) pairs across all of the owner's pets.

        This is how the Scheduler "talks to" the Owner: it walks owner.pets and
        pulls each pet's tasks, keeping the pet attached so the plan can say which
        animal each task belongs to. Completed tasks are skipped — they don't need
        to be planned again today.
        """
        pairs: list[tuple[Pet, Task]] = []
        for pet in self.owner.pets:
            for task in pet.tasks:
                if not task.completed:
                    pairs.append((pet, task))
        return pairs

    def sort_tasks(self, tasks: list[Task]) -> list[Task]:
        """Order tasks by priority (high first), then shorter tasks first.

        Shorter-first as the tie-breaker lets more tasks fit within the budget.
        """
        return sorted(
            tasks,
            key=lambda t: (-t.priority_score(), t.duration_minutes),
        )

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Order tasks chronologically by their preferred_time ("HH:MM").

        The lambda key converts each "HH:MM" string to minutes-since-midnight so
        the sort is numeric and robust. Tasks without a preferred_time sort to the
        end (sentinel of a very large number); higher priority breaks ties when
        two tasks share the same time.
        """
        return sorted(
            tasks,
            key=lambda t: (
                _parse_time(t.preferred_time) if t.preferred_time else 24 * 60,
                -t.priority_score(),
            ),
        )

    def filter_by_status(self, tasks: list[Task], completed: bool) -> list[Task]:
        """Return only tasks whose completion status matches `completed`."""
        return [t for t in tasks if t.completed == completed]

    def filter_by_pet(self, pet_name: str) -> list[Task]:
        """Return the tasks belonging to the named pet (empty if no such pet)."""
        for pet in self.owner.pets:
            if pet.name == pet_name:
                return list(pet.tasks)
        return []

    def detect_conflicts(self) -> list[str]:
        """Return warning strings for tasks whose preferred times overlap.

        Lightweight strategy: for every incomplete task that has a preferred_time,
        compute its [start, end) interval (start = preferred time, end = start +
        duration). Sort by start, then flag any task that begins before the
        previous one ends. This returns a list of human-readable warnings instead
        of raising, so callers can display them and keep running. Tasks with no
        preferred_time are ignored (they float and never "conflict").
        """
        # Build (start, end, pet_name, task) for timed, incomplete tasks.
        timed: list[tuple[int, int, str, Task]] = []
        for pet, task in self.collect_tasks():
            if task.preferred_time:
                start = _parse_time(task.preferred_time)
                timed.append((start, start + task.duration_minutes, pet.name, task))

        timed.sort(key=lambda item: item[0])

        warnings: list[str] = []
        for i in range(1, len(timed)):
            prev_start, prev_end, prev_pet, prev_task = timed[i - 1]
            start, _end, pet_name, task = timed[i]
            if start < prev_end:  # overlap
                same = "same pet" if pet_name == prev_pet else "different pets"
                warnings.append(
                    f"⚠️ Conflict ({same}): '{prev_task.title}' ({prev_pet}, "
                    f"{prev_task.preferred_time}–{_format_time(prev_end)}) overlaps "
                    f"'{task.title}' ({pet_name}, starts {task.preferred_time})."
                )
        return warnings

    def filter_tasks(self, tasks: list[Task], budget: int) -> list[Task]:
        """Greedily keep tasks (in the given order) that fit the time budget.

        Assumes `tasks` is already sorted by importance, so high-priority tasks
        get first claim on the budget before lower-priority ones.
        """
        kept: list[Task] = []
        remaining = budget
        for task in tasks:
            if task.fits_within(remaining):
                kept.append(task)
                remaining -= task.duration_minutes
        return kept

    def build_plan(self) -> list[dict]:
        """Produce an ordered daily plan across all pets, within the time budget.

        Returns a list of dicts, one per scheduled task:
            {"pet", "title", "start", "end", "duration_minutes", "priority", "reason"}

        Times are laid out back-to-back starting from day_start.
        """
        pairs = self.collect_tasks()
        # Sort the (pet, task) pairs using the same task ordering.
        pairs.sort(key=lambda pt: (-pt[1].priority_score(), pt[1].duration_minutes))

        plan: list[dict] = []
        remaining = self.time_budget
        current = _parse_time(self.day_start)
        for pet, task in pairs:
            if not task.fits_within(remaining):
                continue
            start = current
            end = current + task.duration_minutes
            plan.append(
                {
                    "pet": pet.name,
                    "title": task.title,
                    "start": _format_time(start),
                    "end": _format_time(end),
                    "duration_minutes": task.duration_minutes,
                    "priority": task.priority,
                    "reason": self._reason(task, remaining),
                }
            )
            remaining -= task.duration_minutes
            current = end
        return plan

    @staticmethod
    def _reason(task: Task, remaining_before: int) -> str:
        """Explain why this task was chosen and placed here."""
        return (
            f"{task.priority}-priority task; fit within the remaining "
            f"{remaining_before} min of budget"
        )


def _parse_time(hhmm: str) -> int:
    """Convert an 'HH:MM' string to minutes since midnight."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _format_time(total_minutes: int) -> str:
    """Convert minutes since midnight back to an 'HH:MM' string (wraps at 24h)."""
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
