"""Who is logged in, kept in the Streamlit session (stories 1-2)."""

import base64
import json
import re
import time

import streamlit as st

import api_client
import ui

TOKEN_KEY = "auth_token"
USER_KEY = "auth_user"
EXPIRES_AT_KEY = "auth_expires_at"
GO_HOME_KEY = "auth_go_home"
NOTICE_KEY = "auth_notice"
COOKIE_ACTION_KEY = "auth_cookie_action"
COOKIE_CHECKED_KEY = "auth_cookie_checked"

COOKIE_NAME = "coursecorrect_token"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def token_expires_at(token: str) -> float:
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        return float(claims["exp"])
    except (IndexError, KeyError, TypeError, ValueError):
        return 0


def log_in(token: str, user: dict) -> None:
    remember(token, user)
    st.session_state[GO_HOME_KEY] = True
    st.session_state[COOKIE_ACTION_KEY] = "set"


def remember(token: str, user: dict) -> None:
    st.session_state[TOKEN_KEY] = token
    st.session_state[USER_KEY] = user
    st.session_state[EXPIRES_AT_KEY] = token_expires_at(token)


def log_out(notice: str | None = None) -> None:
    for key in (TOKEN_KEY, USER_KEY, EXPIRES_AT_KEY):
        st.session_state.pop(key, None)
    st.session_state[GO_HOME_KEY] = True
    st.session_state[COOKIE_ACTION_KEY] = "clear"
    if notice:
        st.session_state[NOTICE_KEY] = notice


def current_user() -> dict | None:
    return st.session_state.get(USER_KEY)


def get_token() -> str | None:
    return st.session_state.get(TOKEN_KEY)


def should_go_home() -> bool:
    return bool(st.session_state.pop(GO_HOME_KEY, False))


def pop_notice() -> str | None:
    return st.session_state.pop(NOTICE_KEY, None)


def check_session() -> None:
    expires_at = st.session_state.get(EXPIRES_AT_KEY)
    if current_user() and (expires_at is None or time.time() >= expires_at):
        log_out("Your session expired. Please log in again.")


def restore_from_cookie() -> None:
    if st.session_state.get(COOKIE_CHECKED_KEY) or current_user():
        return
    st.session_state[COOKIE_CHECKED_KEY] = True

    token = st.context.cookies.get(COOKIE_NAME)
    if not token:
        return
    if token_expires_at(token) <= time.time():
        st.session_state[COOKIE_ACTION_KEY] = "clear"
        return

    with ui.loading():
        try:
            user = api_client.request("GET", "/auth/me", token=token)
        except api_client.BackendError as exc:
            if exc.status_code == 401:
                st.session_state[COOKIE_ACTION_KEY] = "clear"
            else:  # Backend asleep or down: keep the cookie and try next time.
                st.session_state[NOTICE_KEY] = (
                    "Could not reach the server to restore your login."
                )
            return
    remember(token, user)


def sync_cookie() -> None:
    """Write or delete the login cookie if a login or logout asked for it.

    Call this on a run that displays a page: a run that ends in st.rerun or
    st.switch_page may never reach the browser.
    """
    action = st.session_state.pop(COOKIE_ACTION_KEY, None)
    token = get_token()
    if action == "set" and token and TOKEN_PATTERN.fullmatch(token):
        max_age = int(st.session_state[EXPIRES_AT_KEY] - time.time())
        cookie = f"{COOKIE_NAME}={token}; Max-Age={max(max_age, 0)}"
    elif action == "clear":
        cookie = f"{COOKIE_NAME}=; Max-Age=0"
    else:
        return
    st.html(
        '<div class="cc-cookie-sync"><script>'
        f"document.cookie = {json.dumps(cookie + '; Path=/; SameSite=Strict')}"
        ' + (location.protocol === "https:" ? "; Secure" : "");'
        "</script></div>",
        unsafe_allow_javascript=True,
    )
