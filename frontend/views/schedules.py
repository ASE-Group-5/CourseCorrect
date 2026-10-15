"""Schedule viewing page.

Students and instructors see their own schedule; coordinators can look up
anyone's.
"""

import streamlit as st
from fpdf import FPDF

import api_client
import auth
import ui

st.title("Schedules")

user = auth.current_user()
is_coordinator = user["role"] == "coordinator"


def build_schedule_pdf(classes: list[dict]) -> bytes:
    """Render the student's classes to a simple PDF document."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Class Schedule", ln=True)
    pdf.ln(2)
    for entry in classes:
        pdf.multi_cell(
            0,
            8,
            f"{entry['course_code']} - {entry['course_name']}\n"
            f"Room: {entry['room_name']} ({entry['room_building']})\n"
            f"Time: {entry['time_slot_label']}\n"
            f"Instructor: {entry['instructor_name']}",
        )
        pdf.ln(2)
    return bytes(pdf.output())


if is_coordinator:
    view = st.radio(
        "View schedule for", ["Instructor", "Student"], horizontal=True
    )
else:
    view = user["role"].title()

if view == "Instructor":
    st.subheader("View instructor schedule")
    username = (
        st.text_input("Instructor username")
        if is_coordinator
        else user["username"]
    )

    if st.button("View schedule"):
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

else:
    st.subheader("View student schedule")
    username = (
        st.text_input("Student username")
        if is_coordinator
        else user["username"]
    )

    if st.button("View schedule"):
        with ui.loading():
            try:
                classes = api_client.request(
                    "GET",
                    f"/schedules/student/{username}",
                    token=auth.get_token(),
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
