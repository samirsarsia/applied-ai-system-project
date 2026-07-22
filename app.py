import streamlit as st

from pawpal_system import Owner, Pet, Scheduler, Task

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

# --- Application "memory" -------------------------------------------------
# Streamlit reruns this whole script on every interaction, so a plain
# `owner = Owner(...)` would be recreated (empty) on each click. Instead we
# store a single Owner instance in st.session_state — the session "vault" that
# survives reruns — and check-before-create so it is only built once.
if "owner" not in st.session_state:
    st.session_state.owner = Owner("Jordan", available_minutes=90)

owner = st.session_state.owner  # the same persistent object across reruns

st.subheader("Owner & Pets")
owner.name = st.text_input("Owner name", value=owner.name)

# --- Add a Pet ------------------------------------------------------------
# The form handler builds a Pet from the inputs and hands it to the logic
# layer via Owner.add_pet(). Because `owner` lives in st.session_state, the
# new pet persists; Streamlit reruns after the submit, so the pet selector
# below re-reads owner.pets and shows the addition automatically.
with st.form("add_pet_form", clear_on_submit=True):
    st.markdown("**Add a pet**")
    new_pet_name = st.text_input("New pet name", value="")
    new_pet_species = st.selectbox("New pet species", ["dog", "cat", "other"])
    if st.form_submit_button("Add pet"):
        if new_pet_name.strip():
            owner.add_pet(Pet(new_pet_name.strip(), new_pet_species))
            st.success(f"Added {new_pet_name.strip()} ({new_pet_species}).")
        else:
            st.warning("Give the pet a name first.")

# Ensure the owner has at least one pet to attach tasks to.
if not owner.pets:
    owner.add_pet(Pet("Mochi", "dog"))

# Let the user pick which pet they're adding tasks to.
pet_names = [p.name for p in owner.pets]
selected = st.selectbox("Select a pet to manage", pet_names)
pet = owner.pets[pet_names.index(selected)]
st.caption(f"Managing **{pet.name}** ({pet.species}).")

st.markdown("### Tasks")
st.caption("Tasks are stored on the persisted Owner's pet, so they survive page refreshes.")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
with col4:
    frequency = st.selectbox("Frequency", ["daily", "weekly", "once"], index=0)
with col5:
    preferred_time = st.text_input("Preferred time", value="08:00")

if st.button("Add task"):
    # Append a real Task to the real Pet on the persisted Owner.
    pet.add_task(
        Task(
            title=task_title,
            duration_minutes=int(duration),
            priority=priority,
            frequency=frequency,
            preferred_time=preferred_time.strip() or None,
        )
    )

if pet.tasks:
    st.write("Current tasks:")

    # Use the Scheduler's own methods so the UI reflects the smart logic:
    # filter by completion status, then show in chronological (time) order.
    view_scheduler = Scheduler(owner)
    status_filter = st.radio(
        "Show", ["Pending", "Completed", "All"], horizontal=True, key="status_filter"
    )
    if status_filter == "Pending":
        shown = view_scheduler.filter_by_status(pet.tasks, completed=False)
    elif status_filter == "Completed":
        shown = view_scheduler.filter_by_status(pet.tasks, completed=True)
    else:
        shown = list(pet.tasks)
    shown = view_scheduler.sort_by_time(shown)  # chronological order

    if not shown:
        st.caption("No tasks match this filter.")
    # Show each task with a "Done" button. Completing a recurring task spawns its
    # next occurrence automatically via Pet.complete_task().
    for i, t in enumerate(shown):
        c1, c2 = st.columns([5, 1])
        status = "✅" if t.completed else "⬜"
        when = t.preferred_time or "anytime"
        c1.write(
            f"{status} **{when}** — {t.title} · {t.duration_minutes} min · "
            f"{t.priority} · {t.frequency} (due {t.due_date})"
        )
        if not t.completed:
            if c2.button("Done", key=f"done_{t.title}_{i}"):
                new_task = pet.complete_task(t)
                if new_task is not None:
                    st.success(
                        f"Marked '{t.title}' done. Next {t.frequency} occurrence "
                        f"added for {new_task.due_date}."
                    )
                else:
                    st.success(f"Marked '{t.title}' done.")
                st.rerun()
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("Set how much time you have today, then generate the plan.")

time_budget = st.number_input(
    "Time available today (minutes)", min_value=5, max_value=600, value=90, step=5
)
day_start = st.text_input("Day starts at (HH:MM)", value="08:00")

if st.button("Generate schedule"):
    if not pet.tasks:
        st.warning("Add at least one task before generating a schedule.")
    else:
        # Read straight from the persisted Owner — no rebuilding needed.
        owner.set_available_time(int(time_budget))
        scheduler = Scheduler(owner, day_start=day_start)

        # Surface conflicts first, so the owner sees them before the plan.
        # These are advisory (non-blocking): a conflict means two preferred
        # times overlap, but the plan is still generated. st.warning (yellow)
        # is the right severity — not an error, but something to act on.
        conflicts = scheduler.detect_conflicts()
        if conflicts:
            st.warning(f"⚠️ {len(conflicts)} scheduling conflict(s) found:")
            for warning in conflicts:
                st.warning(warning)
        else:
            st.success("✅ No scheduling conflicts.")

        plan = scheduler.build_plan()

        st.markdown(f"### 🗓️ Today's plan for {owner.name}")
        if not plan:
            st.info("No tasks fit within the available time.")
        else:
            st.table(
                [
                    {
                        "Start": row["start"],
                        "End": row["end"],
                        "Task": row["title"],
                        "Pet": row["pet"],
                        "Priority": row["priority"],
                        "Minutes": row["duration_minutes"],
                    }
                    for row in plan
                ]
            )

            scheduled_min = sum(row["duration_minutes"] for row in plan)
            st.caption(
                f"{len(plan)} of {len(pet.tasks)} tasks scheduled "
                f"· {scheduled_min} of {int(time_budget)} min used."
            )

            # Explain the reasoning for each scheduled task.
            with st.expander("Why this plan?"):
                for row in plan:
                    st.markdown(f"- **{row['title']}** — {row['reason']}")

            # Show anything that didn't fit the budget.
            scheduled_titles = {row["title"] for row in plan}
            skipped = [t.title for t in pet.tasks if t.title not in scheduled_titles]
            if skipped:
                st.warning("Skipped (over budget): " + ", ".join(skipped))
