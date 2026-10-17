"""Account creation page (story 2). New accounts are students."""

import streamlit as st

import api_client
import auth
import ui

ui.narrow_page()

st.title("Create account")

with st.form("register"):
    full_name = st.text_input("Full name")
    username = st.text_input(
        "Username", help="3-50 letters, digits, dots or underscores."
    )
    email = st.text_input("Email")
    password = st.text_input(
        "Password", type="password", help="At least 8 characters."
    )
    confirm = st.text_input("Confirm password", type="password")
    submitted = st.form_submit_button("Create account", type="primary")

if submitted:
    problems = []
    if not all(
        value.strip() for value in (full_name, username, email, password)
    ):
        problems.append("Fill in every field.")
    if password != confirm:
        problems.append("Passwords do not match.")

    if problems:
        st.error("Please enter valid information:\n\n" + "\n\n".join(problems))
    else:
        with ui.loading():
            try:
                result = api_client.request(
                    "POST",
                    "/auth/register",
                    json={
                        "username": username,
                        "email": email,
                        "full_name": full_name,
                        "password": password,
                    },
                )
            except api_client.BackendError as exc:
                if exc.status_code in (409, 422):
                    lines = exc.detail.replace("\n", "\n\n")
                    st.error(f"Please enter valid information:\n\n{lines}")
                else:
                    st.error(str(exc))
            else:
                auth.log_in(result["access_token"], result["user"])
                st.rerun()

st.page_link("views/login.py", label="Already have an account? Log in")
