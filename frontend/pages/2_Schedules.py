"""Schedule viewing page."""

import streamlit as st
from fpdf import FPDF

import api_client

st.title("Schedules")


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


view = st.radio("View schedule for", ["Instructor", "Student"], horizontal=True)

if view == "Instructor":
    st.subheader("View instructor schedule")
    username = st.text_input("Instructor username")

    if st.button("View schedule"):
        with st.spinner(
            "Contacting backend (may take a minute if it was asleep)..."
        ):
            try:
                classes = api_client.request(
                    "GET", f"/schedules/instructor/{username}"
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
    username = st.text_input("Student username")

    if st.button("View schedule"):
        with st.spinner(
            "Contacting backend (may take a minute if it was asleep)..."
        ):
            try:
                classes = api_client.request(
                    "GET", f"/schedules/student/{username}"
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
