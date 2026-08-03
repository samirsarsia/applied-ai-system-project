import os

import streamlit as st
from dotenv import load_dotenv

import agent
import storage
from pawpal_system import Owner, Pet, Scheduler, Task

load_dotenv()

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

# --- Global styling ---------------------------------------------------------
# Every custom element below sets its OWN background AND text color together
# (never relies on Streamlit's inherited theme color against a custom
# background) so nothing can end up low-contrast or invisible depending on
# whether the viewer is in light or dark mode.
st.markdown(
    """
<style>
    div[data-testid="stMetric"] {
        background: #eef2f6;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        border: 1px solid #c7d0da;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] div {
        color: #1a1a1a !important;
    }
    .pawpal-hero {
        padding: 1.25rem 1.5rem;
        border-radius: 16px;
        background: #c0392b;
        margin-bottom: 1rem;
    }
    .pawpal-hero h1, .pawpal-hero p {
        color: #ffffff !important;
    }
    .pawpal-hero h1 { margin: 0; font-size: 1.7rem; }
    .pawpal-hero p { margin: 0.25rem 0 0 0; }
    .task-card {
        border-radius: 10px;
        padding: 0.6rem 0.9rem;
        margin-bottom: 0.4rem;
        border: 1px solid #c7d0da;
        background: #f4f6f8;
        color: #1a1a1a;
    }
    .task-card b { color: #1a1a1a; }
    .chip {
        display: inline-block;
        border-radius: 999px;
        padding: 0.1rem 0.7rem;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 0.4rem;
    }
    .chip-high { background: #c0392b; color: #ffffff; }
    .chip-medium { background: #b8860b; color: #ffffff; }
    .chip-low { background: #2e7d32; color: #ffffff; }
    .advisor-bubble {
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        background: #fdece5;
        border: 1px solid #e8896b;
        margin: 0.6rem 0;
        color: #1a1a1a;
    }
</style>
""",
    unsafe_allow_html=True,
)

PRIORITY_CHIP = {"high": "chip-high", "medium": "chip-medium", "low": "chip-low"}

# --- Application "memory" -------------------------------------------------
# Streamlit reruns this whole script on every interaction, so a plain
# `owner = Owner(...)` would be recreated (empty) on each click. We keep a
# single Owner instance in st.session_state so it survives reruns *within* a
# browser session, AND persist it to data/owner.json (storage.py) on every
# change, so a full server restart (or opening the app again tomorrow)
# reloads the same pets, tasks, and schedule instead of starting over.
if "owner" not in st.session_state:
    st.session_state.owner = storage.load_owner() or Owner("Jordan", available_minutes=90)
if "advisor_history" not in st.session_state:
    st.session_state.advisor_history = []

owner = st.session_state.owner  # the same persistent object across reruns

st.markdown(
    """
<div class="pawpal-hero">
<h1>🐾 PawPal+ Care Advisor</h1>
<p>Plan your pets' day, and ask your AI advisor to adjust it in plain English.</p>
</div>
""",
    unsafe_allow_html=True,
)

gemini_ready = bool(os.environ.get("GEMINI_API_KEY"))

with st.sidebar:
    st.markdown("### 🤖 Advisor status")
    if gemini_ready:
        st.success("Live Gemini reasoning is **on**.")
    else:
        st.info("Running the **offline** rule-based planner (no GEMINI_API_KEY set).")
    st.divider()
    st.markdown("### 💾 Data")
    st.caption(f"Autosaved to `{storage.DEFAULT_DATA_PATH}` after every change.")
    if st.button("🗑️ Reset all data", use_container_width=True):
        st.session_state.owner = Owner("Jordan", available_minutes=90)
        st.session_state.advisor_history = []
        storage.save_owner(st.session_state.owner)
        st.rerun()

owner.name = st.sidebar.text_input("Owner name", value=owner.name)

tab_pets, tab_schedule, tab_advisor = st.tabs(["🐶 Pets & Tasks", "🗓️ Schedule", "💬 Care Advisor"])

# ============================================================ Pets & Tasks
with tab_pets:
    col_add, col_manage = st.columns([1, 2], gap="large")

    with col_add:
        st.markdown("#### Add a pet")
        with st.form("add_pet_form", clear_on_submit=True):
            new_pet_name = st.text_input("Name", value="", placeholder="e.g. Mochi")
            new_pet_species = st.selectbox("Species", ["dog", "cat", "other"])
            if st.form_submit_button("Add pet", use_container_width=True):
                if new_pet_name.strip():
                    owner.add_pet(Pet(new_pet_name.strip(), new_pet_species))
                    st.success(f"Added {new_pet_name.strip()} ({new_pet_species}).")
                else:
                    st.warning("Give the pet a name first.")

        if not owner.pets:
            owner.add_pet(Pet("Mochi", "dog"))

        st.markdown("#### Your pets")
        for p in owner.pets:
            icon = "🐕" if p.species == "dog" else "🐈" if p.species == "cat" else "🐾"
            st.write(f"{icon} **{p.name}** · {len(p.tasks)} task(s)")

    with col_manage:
        pet_names = [p.name for p in owner.pets]
        selected = st.selectbox("Managing tasks for", pet_names)
        pet = owner.pets[pet_names.index(selected)]

        st.markdown("#### Add a task")
        with st.form("add_task_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                task_title = st.text_input("Title", value="", placeholder="Morning walk")
                priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
            with c2:
                duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
                frequency = st.selectbox("Frequency", ["daily", "weekly", "once"], index=0)
            with c3:
                preferred_time = st.text_input("Preferred time (HH:MM)", value="08:00")
            if st.form_submit_button("➕ Add task", use_container_width=True):
                if task_title.strip():
                    pet.add_task(
                        Task(
                            title=task_title.strip(),
                            duration_minutes=int(duration),
                            priority=priority,
                            frequency=frequency,
                            preferred_time=preferred_time.strip() or None,
                        )
                    )
                    st.success(f"Added '{task_title.strip()}' for {pet.name}.")
                else:
                    st.warning("Give the task a title first.")

        st.markdown(f"#### {pet.name}'s tasks")
        if pet.tasks:
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
            shown = view_scheduler.sort_by_time(shown)

            if not shown:
                st.caption("No tasks match this filter.")
            for i, t in enumerate(shown):
                c1, c2 = st.columns([5, 1])
                status = "✅" if t.completed else "⬜"
                when = t.preferred_time or "anytime"
                chip = PRIORITY_CHIP.get(t.priority, "chip-medium")
                c1.markdown(
                    f'<div class="task-card">{status} <b>{when}</b> — {t.title} '
                    f'· {t.duration_minutes} min · {t.frequency} (due {t.due_date}) '
                    f'<span class="chip {chip}">{t.priority}</span></div>',
                    unsafe_allow_html=True,
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
            st.info("No tasks yet — add one above.")

# ================================================================ Schedule
with tab_schedule:
    st.markdown("#### Build today's schedule")
    c1, c2 = st.columns(2)
    with c1:
        time_budget = st.number_input(
            "Time available today (minutes)", min_value=5, max_value=600, value=owner.available_minutes, step=5
        )
    with c2:
        day_start = st.text_input("Day starts at (HH:MM)", value="08:00")

    all_pet_tasks = [t for p in owner.pets for t in p.tasks]

    if st.button("✨ Generate schedule", type="primary", use_container_width=True):
        if not all_pet_tasks:
            st.warning("Add at least one task before generating a schedule.")
        else:
            owner.set_available_time(int(time_budget))
            scheduler = Scheduler(owner, day_start=day_start)

            conflicts = scheduler.detect_conflicts()
            plan = scheduler.build_plan()
            scheduled_min = sum(row["duration_minutes"] for row in plan)

            m1, m2, m3 = st.columns(3)
            m1.metric("Tasks scheduled", f"{len(plan)}/{len(all_pet_tasks)}")
            m2.metric("Minutes used", f"{scheduled_min}/{int(time_budget)}")
            m3.metric("Conflicts", len(conflicts), delta=None)

            if conflicts:
                st.warning(f"⚠️ {len(conflicts)} scheduling conflict(s):")
                for warning in conflicts:
                    st.warning(warning)
            else:
                st.success("✅ No scheduling conflicts.")

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

                with st.expander("Why this plan?"):
                    for row in plan:
                        st.markdown(f"- **{row['title']}** — {row['reason']}")

                scheduled_titles = {row["title"] for row in plan}
                skipped = [t.title for t in all_pet_tasks if t.title not in scheduled_titles]
                if skipped:
                    st.warning("Skipped (over budget): " + ", ".join(skipped))
    else:
        st.caption("Set a time budget and click Generate to see today's plan.")

# ================================================================ Advisor
with tab_advisor:
    st.markdown("#### 💬 Ask your Care Advisor")
    st.caption(
        "The agent inspects and adjusts the real schedule (same data as the other tabs), "
        "then double-checks its own work before replying."
    )
    if not gemini_ready:
        st.info(
            "No **GEMINI_API_KEY** is set, so the advisor is running in **offline simulation "
            "mode** (a deterministic rule-based stand-in for the LLM planner — see `agent.py`). "
            "Add `GEMINI_API_KEY` to your `.env` file and restart to enable live Gemini reasoning."
        )

    for turn in st.session_state.advisor_history:
        with st.chat_message("user"):
            st.write(turn["message"])
        with st.chat_message("assistant"):
            badge = {
                "live-llm": "🟢 live Gemini",
                "guardrail": "🟡 safety guardrail",
            }.get(turn["mode"], "🔵 offline simulation")
            st.markdown(f"*{badge} · confidence {turn['confidence']:.2f}*")
            st.markdown(f'<div class="advisor-bubble">{turn["reply"]}</div>', unsafe_allow_html=True)
            with st.expander("Reasoning trace (plan → act → verify)"):
                for step in turn["trace"]:
                    if step["step"] == "tool_call":
                        st.write(f"🔧 `{step['tool']}({step['args']})` → `{step['result']}`")
                    else:
                        st.write(f"• **{step['step']}**: {step.get('detail', '')}")

    user_message = st.chat_input(
        placeholder="e.g. Mochi seems tired today, can you lighten the schedule?"
    )
    if user_message:
        result = agent.run(owner, user_message)
        st.session_state.advisor_history.append(
            {
                "message": user_message,
                "reply": result.reply,
                "mode": result.mode,
                "confidence": result.confidence,
                "trace": result.trace,
            }
        )
        st.rerun()

# Streamlit reruns this whole script top-to-bottom on every interaction, so
# saving once here — after every rerun, regardless of which control triggered
# it — persists every mutation above (add pet, add task, mark done, generate
# schedule, agent tool calls) without needing a save call at each site.
storage.save_owner(owner)
