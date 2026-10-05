"""Frontend configuration."""

import os

DEFAULT_BACKEND_URL = "http://localhost:8000"


def get_backend_url() -> str:
    """Returns the backend base URL.

    Order of precedence: BACKEND_URL env var, Streamlit secrets, default.
    """
    env_value = os.getenv("BACKEND_URL")
    if env_value:
        return env_value.rstrip("/")
    try:
        import streamlit as st  # pylint: disable=import-outside-toplevel

        secret_value = st.secrets.get("BACKEND_URL")
        if secret_value:
            return str(secret_value).rstrip("/")
    except Exception:  # pylint: disable=broad-except
        pass  # No secrets file configured; fall through to the default.
    return DEFAULT_BACKEND_URL
