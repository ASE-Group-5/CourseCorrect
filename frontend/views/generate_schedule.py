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
    fitness, found, run = st.columns(3)
    fitness.metric("Fitness", result["fitness"])
    found.metric("Best found in generation", result["generation_found"])
    run.metric("Generations run", result["generations_run"])

    conflicts = result["hard_violations"]
    if conflicts:
        st.error(f"{len(conflicts)} conflict(s) remain:")
        st.markdown("\n".join(f"- {c}" for c in conflicts))
    else:
        st.success("No conflicts.")

    unmet = result["soft_violations"]
    with st.expander(f"Preferences not met ({len(unmet)})"):
        if unmet:
            st.markdown("\n".join(f"- {v}" for v in unmet))
        else:
            st.write("None.")


st.subheader("Schedules this semester")
schedule_admin.semester_schedules()
