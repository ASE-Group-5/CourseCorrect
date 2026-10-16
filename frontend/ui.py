"""Shared look and feel: global styles and the loading indicator.

Colors, fonts and text size live in `.streamlit/config.toml`; this module
only adds what the theme cannot express.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

STYLES = """
<style>
.cc-loader {
    display: flex;
    justify-content: center;
    padding: 1.5rem 0;
}
.cc-loader-ring {
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 50%;
    border: 0.3rem solid rgba(46, 91, 255, 0.18);
    border-top-color: #2E5BFF;
    animation: cc-spin 0.8s linear infinite;
}
@keyframes cc-spin {
    to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
    .cc-loader-ring { animation-duration: 2.4s; }
}
.cc-visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
}

/* Room for wide tables at the larger text size. */
[data-testid="stMain"] [data-testid="stMainBlockContainer"] {
    max-width: 64rem;
}

/* The one-off login-cookie script (auth.sync_cookie) takes no space. */
[data-testid="stElementContainer"]:has(.cc-cookie-sync) {
    display: none;
}

/* Forms read as cards on the lighter page background. */
[data-testid="stForm"] {
    background: #FFFFFF;
    padding: 1.5rem 1.5rem 1rem;
}
</style>
"""

# More specific than the site-wide width above, so it wins on pages that use it.
NARROW_PAGE = """
<style>
[data-testid="stApp"] [data-testid="stMain"] [data-testid="stMainBlockContainer"] {
    max-width: 38rem;
}
</style>
"""

LOADER = (
    '<div class="cc-loader" role="status">'
    '<div class="cc-loader-ring"></div>'
    '<span class="cc-visually-hidden">Loading</span>'
    "</div>"
)


def apply_styles() -> None:
    """Add the site-wide styles. Call once per run, before any page."""
    st.html(STYLES)


def narrow_page() -> None:
    """Use a narrow, centered column (for short forms like login)."""
    st.html(NARROW_PAGE)


@contextmanager
def loading() -> Iterator[None]:
    """Show a spinning loader while the block runs (e.g. a backend call)."""
    placeholder = st.empty()
    placeholder.markdown(LOADER, unsafe_allow_html=True)
    try:
        yield
    finally:
        placeholder.empty()
