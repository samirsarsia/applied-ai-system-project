"""Tests for the PawPal+ persistence layer (storage.py).

Run with:  python -m pytest

Uses tmp_path (pytest's built-in temp directory fixture) so tests never touch
the real data/owner.json file used by the running app.
"""

from datetime import date

from pawpal_system import Owner, Pet, Task

import storage


def _sample_owner() -> Owner:
    owner = Owner("Jordan", available_minutes=90, preferences={"quiet_hours": "22:00-07:00"})
    dog = Pet("Mochi", "dog")
    dog.add_task(Task("Morning walk", 30, "high", preferred_time="08:00", frequency="daily"))
    cat = Pet("Whiskers", "cat")
    cat.add_task(Task("Feed cat", 5, "high", preferred_time="08:15", frequency="daily"))
    cat.tasks[0].mark_complete()
    owner.add_pet(dog)
    owner.add_pet(cat)
    return owner


def test_save_then_load_round_trips_all_fields(tmp_path):
    path = str(tmp_path / "owner.json")
    original = _sample_owner()

    storage.save_owner(original, path)
    loaded = storage.load_owner(path)

    assert loaded is not None
    assert loaded.name == "Jordan"
    assert loaded.available_minutes == 90
    assert loaded.preferences == {"quiet_hours": "22:00-07:00"}
    assert [p.name for p in loaded.pets] == ["Mochi", "Whiskers"]

    walk = loaded.pets[0].tasks[0]
    assert walk.title == "Morning walk"
    assert walk.duration_minutes == 30
    assert walk.priority == "high"
    assert walk.preferred_time == "08:00"
    assert walk.completed is False

    feed = loaded.pets[1].tasks[0]
    assert feed.completed is True
    assert feed.due_date == date.today()


def test_load_missing_file_returns_none(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    assert storage.load_owner(path) is None


def test_load_corrupt_file_returns_none_not_exception(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{ this is not valid json ]")

    assert storage.load_owner(str(path)) is None


def test_save_creates_parent_directories(tmp_path):
    path = str(tmp_path / "nested" / "dir" / "owner.json")
    storage.save_owner(_sample_owner(), path)

    assert storage.load_owner(path) is not None


def test_save_overwrites_existing_file(tmp_path):
    path = str(tmp_path / "owner.json")
    storage.save_owner(_sample_owner(), path)

    smaller = Owner("Alex", available_minutes=15)
    storage.save_owner(smaller, path)

    loaded = storage.load_owner(path)
    assert loaded.name == "Alex"
    assert loaded.pets == []
