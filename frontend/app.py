"""CourseCorrect Streamlit frontend: home page."""

import streamlit as st

import api_client
from config import get_backend_url

st.set_page_config(page_title="CourseCorrect", page_icon="📅")

st.title("CourseCorrect")
st.write("Smart, adjustable semester scheduling for universities.")

st.subheader("System status")
st.caption(f"Backend: {get_backend_url()}")

if st.button("Check backend connection"):
    with st.spinner(
        "Contacting backend (may take a minute if it was asleep)..."
    ):
        try:
            api_client.get_health()
            st.success("Backend is reachable.")
            api_client.get_db_health()
            st.success("Database is connected.")
        except api_client.BackendError as exc:
            st.error(str(exc))
