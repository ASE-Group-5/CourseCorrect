"""Schedule viewing page."""

import streamlit as st
from fpdf import FPDF

import api_client
import auth
import schedule_admin
import ui

st.title("Schedules")

user = auth.current_user()
is_coordinator = user["role"] == "coordinator"
is_instructor = user["role"] == "instructor"


def build_schedule_pdf(classes: list[dict]) -> bytes:
    """Render the student's classes to a simple PDF document."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, "Class Schedule", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", size=12)
    with pdf.table() as table:
        table.row(("Course Code", "Course Name", "Room", "Time", "Instructor"))
        for entry in classes:
            table.row(
                (
                    str(entry["course_code"]),
                    str(entry["course_name"]),
                    f"{entry['room_name']} ({entry['room_building']})",
                    str(entry["time_slot_label"]),
                    str(entry["instructor_name"]),
                )
            )
    return bytes(pdf.output())


def choose_user(role: str) -> str | None:
    """Return the username a coordinator picks from the active `role` users."""
    try:
        people = api_client.request(
            "GET",
            "/users",
            token=auth.get_token(),
            params={"role": role, "include_inactive": False},
        )
    except api_client.BackendError as exc:
        st.error(str(exc))
        return None
    names = {
        p["username"]: f"{p['full_name']} ({p['username']})" for p in people
    }
    return st.selectbox(role.title(), list(names), format_func=names.get)


def show_calendar_connection_result() -> None:
    result = st.query_params.get("calendar_connection")
    if not result:
        return

    st.query_params.pop("calendar_connection", None)
    if result == "connected":
        st.success("Google Calendar account updated.")
    elif result == "cancelled":
        st.info(
            "Google authorization was cancelled; your existing connection, "
            "if any, is unchanged."
        )
    elif result == "failed":
        st.error(
            "Google authorization failed; your existing connection, if any, "
            "is unchanged. Please try again."
        )


if is_coordinator:
    view = st.radio(
        "View schedule for",
        ["Semester", "Instructor", "Student"],
        horizontal=True,
    )
else:
    view = user["role"].title()

if view == "Semester":
    st.subheader("Published schedule")
    schedule_admin.published_schedule()
elif view == "Instructor":
    st.subheader("View instructor schedule")
    username = choose_user("instructor") if is_coordinator else user["username"]

    if st.button("View schedule", disabled=not username):
        with ui.loading():
            try:
                classes = api_client.request(
                    "GET",
                    f"/schedules/instructor/{username}",
                    token=auth.get_token(),
                )
            except api_client.BackendError as exc:
                st.error(str(exc))
            else:
                if classes:
                    st.table(classes)
                else:
                    st.info("No scheduled classes found.")

    if is_instructor and st.button("Push to Calendar"):
        with ui.loading():
            try:
                result = api_client.request(
                    "POST", "/calendar/push", token=auth.get_token()
                )
            except api_client.BackendError as exc:
                st.error(exc.detail)
            else:
                events_created = result.get("events_created")
                if events_created is None:
                    st.error(
                        "Calendar synchronization returned an invalid response."
                    )
                else:
                    st.success(f"Created {events_created} calendar event(s).")

    if is_instructor:
        show_calendar_connection_result()
        try:
            calendar_status = api_client.request(
                "GET", "/calendar/status", token=auth.get_token()
            )
        except api_client.BackendError as exc:
            st.error(exc.detail)
        else:
            if calendar_status.get("demo_dates_enabled"):
                st.info("Demo Dates enabled: Spring 2027, Mondays/Wednesdays")
            if calendar_status.get("connected"):
                st.success("Google Calendar connected.")
                connection_action = "Change Google Account"
            else:
                if calendar_status.get("reconnect_required"):
                    st.warning(
                        "Google Calendar authorization is no longer valid."
                    )
                    connection_action = "Reconnect Google Calendar"
                else:
                    st.info("Google Calendar is not connected.")
                    connection_action = "Connect Google Calendar"
            if st.button(connection_action):
                with ui.loading():
                    try:
                        auth_url = api_client.request(
                            "GET",
                            "/calendar/oauth/connect",
                            token=auth.get_token(),
                        )["authorization_url"]
                    except api_client.BackendError as exc:
                        st.error(exc.detail)
                    else:
                        st.link_button("Continue with Google", auth_url)

else:
    st.subheader("View student schedule")
    username = choose_user("student") if is_coordinator else user["username"]

    params = None
    if is_coordinator:
        show = st.button("View schedule", disabled=not username)
    else:
        show = False
        try:
            semesters = api_client.request(
                "GET",
                f"/schedules/student/{username}/semesters",
                token=auth.get_token(),
            )
        except api_client.BackendError as exc:
            st.error(str(exc))
            semesters = []
        if semesters:
            chosen = st.selectbox(
                "Semester", semesters, format_func=lambda s: s["name"]
            )
            params = {"semester_id": chosen["id"]}
            show = True

    if show:
        with ui.loading():
            try:
                classes = api_client.request(
                    "GET",
                    f"/schedules/student/{username}",
                    token=auth.get_token(),
                    params=params,
                )
            except api_client.BackendError as exc:
                st.error(str(exc))
            else:
                if classes:
                    st.table(classes)
                    st.download_button(
                        "Download as PDF",
                        data=build_schedule_pdf(classes),
                        file_name="schedule.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.info("No scheduled classes found.")
