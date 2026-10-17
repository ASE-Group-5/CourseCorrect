"""Instructor dashboard: where instructors land after logging in (stories 1-2)."""

import streamlit as st

import auth

user = auth.current_user()

st.title("Instructor dashboard")
st.write(f"Welcome, {user['full_name']}.")
