"""Coordinator views of the semester's schedules."""

import streamlit as st

import api_client
import auth
import ui

FLASH_KEY = "publish_flash"


def publish(schedule_id: int) -> None:
    with ui.loading():
        try:
            outcome = api_client.request(
                "POST",
                f"/schedules/{schedule_id}/publish",
                token=auth.get_token(),
            )
        except api_client.BackendError as exc:
            st.error(f"Could not publish: {exc.detail}")
            return
    message = f"Published schedule #{outcome['schedule_id']}."
    for old_id in outcome["unpublished"]:
        message += f" Schedule #{old_id} is now a draft."
    if outcome["declined"]:
        message += (
            f" {outcome['declined']} pending change request(s) on it "
            "were declined."
        )
    st.session_state[FLASH_KEY] = message
    st.rerun()


def label(schedule: dict) -> str:
    return f"#{schedule['id']} ({schedule['status']})"


def load_schedules() -> list[dict] | None:
    try:
        return api_client.request("GET", "/schedules", token=auth.get_token())
    except api_client.BackendError as exc:
        st.error(str(exc))
        return None


def show_classes(schedule_id: int) -> bool:
    """Show a schedule's classes; False if they could not be loaded."""
    try:
        classes = api_client.request(
            "GET", f"/schedules/{schedule_id}/entries", token=auth.get_token()
        )
    except api_client.BackendError as exc:
        st.error(str(exc))
        return False
    st.dataframe(
        [
            {
                "Course": c["course_code"],
                "Name": c["course_name"],
                "Time": c["time_slot_label"],
                "Room": f"{c['room_name']} ({c['room_building']})",
                "Instructor": c["instructor_name"],
            }
            for c in classes
        ],
        hide_index=True,
        width="stretch",
    )
    return True


def published_schedule() -> None:
    """Show the semester's published schedule, read-only."""
    schedules = load_schedules()
    if schedules is None:
        return
    published = [s for s in schedules if s["status"] == "published"]
    if not published:
        st.info("No schedule has been published for this semester yet.")
        return
    show_classes(published[0]["id"])


def semester_schedules() -> None:
    """List the semester's schedules; view any one and publish drafts."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)

    schedules = load_schedules()
    if schedules is None:
        return
    if not schedules:
        st.info("No schedules for this semester yet.")
        return

    st.dataframe(
        [
            {
                "Schedule": f"#{s['id']}",
                "Status": s["status"].title(),
                "Fitness": s["fitness"],
                "Conflicts": s["conflicts"],
                "Classes": s["classes"],
                "Created": (s["created_at"] or "")[:16].replace("T", " "),
                "Created by": s["created_by"] or "",
            }
            for s in schedules
        ],
        hide_index=True,
        width="stretch",
    )

    by_id = {s["id"]: s for s in schedules}
    published = [s["id"] for s in schedules if s["status"] == "published"]
    schedule_id = st.selectbox(
        "View schedule",
        list(by_id),
        index=list(by_id).index(published[0]) if published else 0,
        format_func=lambda sid: label(by_id[sid]),
    )
    chosen = by_id[schedule_id]

    if not show_classes(schedule_id):
        return

    if chosen["status"] == "published":
        st.caption(f"Schedule #{schedule_id} is the published schedule.")
    elif chosen["conflicts"]:
        st.caption(
            f"Schedule #{schedule_id} has {chosen['conflicts']} conflict(s) "
            "and cannot be published."
        )
    elif st.button(f"Publish schedule #{schedule_id}", type="primary"):
        publish(schedule_id)
