"""Login page (story 1)."""

import streamlit as st

import api_client
import auth
import ui

ui.narrow_page()

st.title("Log in")

notice = auth.pop_notice()
if notice:
    st.warning(notice)

with st.form("login"):
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Log in", type="primary")

if submitted:
    with ui.loading():
        try:
            result = api_client.request(
                "POST",
                "/auth/login",
                json={"username": username, "password": password},
            )
        except api_client.BackendError as exc:
            if exc.status_code in (401, 422):
                st.error("Invalid login")
            else:
                st.error(str(exc))
        else:
            auth.log_in(result["access_token"], result["user"])
            st.rerun()

st.page_link("views/register.py", label="No account? Create one")
