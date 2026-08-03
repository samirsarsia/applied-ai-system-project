"""Persistence layer for PawPal+.

Saves/loads an Owner (with all pets and tasks) to a local JSON file, so the
Streamlit app's data survives a server restart instead of living only in
`st.session_state` memory. This is plain, dependency-free JSON — no database
server to stand up, which matches the "clear setup steps" requirement: no one
running this project needs to install or configure anything beyond
`requirements.txt`.
"""

from __future__ import annotations

import json
import os
from datetime import date

from pawpal_system import Owner, Pet, Task

DEFAULT_DATA_PATH = os.path.join("data", "owner.json")


def _task_to_dict(task: Task) -> dict:
    return {
        "title": task.title,
        "duration_minutes": task.duration_minutes,
        "priority": task.priority,
        "preferred_time": task.preferred_time,
        "frequency": task.frequency,
        "completed": task.completed,
        "due_date": task.due_date.isoformat(),
    }


def _task_from_dict(data: dict) -> Task:
    return Task(
        title=data["title"],
        duration_minutes=data["duration_minutes"],
        priority=data.get("priority", "medium"),
        preferred_time=data.get("preferred_time"),
        frequency=data.get("frequency", "daily"),
        completed=data.get("completed", False),
        due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else date.today(),
    )


def owner_to_dict(owner: Owner) -> dict:
    """Serialize an Owner (and everything it owns) to a plain JSON-safe dict."""
    return {
        "name": owner.name,
        "available_minutes": owner.available_minutes,
        "preferences": owner.preferences,
        "pets": [
            {
                "name": pet.name,
                "species": pet.species,
                "tasks": [_task_to_dict(t) for t in pet.tasks],
            }
            for pet in owner.pets
        ],
    }


def owner_from_dict(data: dict) -> Owner:
    """Rebuild an Owner (and its pets/tasks) from `owner_to_dict()` output."""
    owner = Owner(
        name=data["name"],
        available_minutes=data.get("available_minutes", 0),
        preferences=data.get("preferences", {}),
    )
    for pet_data in data.get("pets", []):
        pet = Pet(name=pet_data["name"], species=pet_data["species"])
        for task_data in pet_data.get("tasks", []):
            pet.add_task(_task_from_dict(task_data))
        owner.add_pet(pet)
    return owner


def save_owner(owner: Owner, path: str = DEFAULT_DATA_PATH) -> None:
    """Write the owner's full state to `path` as JSON. Creates parent dirs
    as needed. Never raises on a write failure — logs to stderr instead, so a
    disk/permissions problem degrades to "changes aren't saved this session"
    rather than crashing the whole app."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(owner_to_dict(owner), f, indent=2)
    except OSError as exc:
        print(f"[storage] warning: could not save to {path}: {exc}")


def load_owner(path: str = DEFAULT_DATA_PATH) -> Owner | None:
    """Read an Owner back from `path`. Returns None if the file doesn't exist
    or is corrupt (logging the reason), so the caller can fall back to a
    fresh Owner instead of crashing on a bad/missing save file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return owner_from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"[storage] warning: could not load {path}, starting fresh: {exc}")
        return None
