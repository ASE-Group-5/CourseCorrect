"""CourseCorrect Streamlit frontend: the entry point and page gate.

Only the pages the current user may see are registered with `st.navigation`,
so any other page cannot be opened, even by typing its URL. The backend
checks every request again; this gate only decides what is shown.

Page scripts live in `views/`, not `pages/`: if a `pages/` folder exists,
Streamlit serves the scripts in it directly and this gate is skipped.
"""

import streamlit as st

import auth
import ui

st.set_page_config(page_title="CourseCorrect", page_icon="📅")
ui.apply_styles()


def log_out() -> None:
    auth.log_out()
    st.rerun()


LOGIN = st.Page("views/login.py", title="Log in", default=True)
REGISTER = st.Page("views/register.py", title="Create account")
SCHEDULES = st.Page("views/schedules.py", title="Schedules")
REQUESTS = st.Page("views/modification_requests.py", title="Requests")
USERS = st.Page("views/user_management.py", title="Users", url_path="users")
LOG_OUT = st.Page(log_out, title="Log out", url_path="logout")


def dashboard(role: str) -> st.Page:
    return st.Page(
        f"views/{role}_dashboard.py",
        title="Dashboard",
        url_path="dashboard",
        default=True,
    )


# Pages each role may open. The first page is where the user lands.
PAGES_BY_ROLE = {
    "student": [dashboard("student"), SCHEDULES, LOG_OUT],
    "instructor": [dashboard("instructor"), SCHEDULES, REQUESTS, LOG_OUT],
    "coordinator": [
        dashboard("coordinator"),
        SCHEDULES,
        REQUESTS,
        USERS,
        LOG_OUT,
    ],
}
LOGGED_OUT_PAGES = [LOGIN, REGISTER]

# Every page change or click reruns this file, so these checks run each time:
# restore a saved login after a refresh, then end it if it has expired.
auth.restore_from_cookie()
auth.check_session()

user = auth.current_user()
pages = PAGES_BY_ROLE[user["role"]] if user else LOGGED_OUT_PAGES
navigation = st.navigation(pages)

if auth.should_go_home():
    st.switch_page(pages[0])

auth.sync_cookie()
navigation.run()
