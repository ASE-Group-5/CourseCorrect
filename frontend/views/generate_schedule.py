"""Schedule generation page (coordinators)."""

import streamlit as st

import api_client
import auth
import schedule_admin
import ui

st.title("Generate schedule")
st.write(
    "Builds a draft schedule for the active semester. "
    "This can take a few seconds."
)

if st.button("Generate schedule", type="primary"):
    with ui.loading():
        try:
            st.session_state["generated_schedule"] = api_client.request(
                "POST",
                "/schedules/generate",
                token=auth.get_token(),
                json={},
            )
        except api_client.BackendError as exc:
            st.session_state.pop("generated_schedule", None)
            st.error("Could not generate a schedule:")
            st.code(exc.detail)

result = st.session_state.get("generated_schedule")
if result:
    st.success(f"Draft schedule #{result['schedule_id']} saved.")

    for kind, title in (
        ("hard", "Hard constraints (Must haves)"),
        ("soft", "Soft constraints (Optional, but preferred)"),
    ):
        st.subheader(title)
        for constraint in result["constraints"]:
            if constraint["kind"] != kind:
                continue
            if constraint["met"]:
                icon = "✅"
            else:
                icon = "❌" if kind == "hard" else "⚠️"
            st.markdown(f"{icon} {constraint['name']}")

    details = result["hard_violations"] + result["soft_violations"]
    if details:
        with st.expander(f"Why some constraints aren't met ({len(details)})"):
            st.markdown("\n".join(f"- {d}" for d in details))


st.subheader("Schedules this semester")
schedule_admin.semester_schedules()
