"""Modification requests"""

import streamlit as st

import api_client
import auth
import ui

st.title("Requests")

user = auth.current_user()
is_coordinator = user["role"] == "coordinator"
token = auth.get_token()


def call(method: str, path: str, **kwargs):
    return api_client.request(method, path, token=token, **kwargs)


def review(request_id: int, accept: bool, comment: str) -> None:
    with ui.loading():
        try:
            call(
                "POST",
                f"/modifications/{request_id}/review",
                json={"accept": accept, "comment": comment or None},
            )
        except api_client.BackendError as exc:
            st.error(str(exc))
        else:
            st.toast("Request accepted" if accept else "Request declined")
            st.rerun()


try:
    options = call("GET", "/modifications/options")
except api_client.BackendError as exc:
    st.error(str(exc))
    st.stop()

if not is_coordinator:
    st.subheader("Request a change")
    entries = {
        f"{e['course_code']} - {e['time_slot_label']}, {e['room_name']}": e[
            "id"
        ]
        for e in options["my_entries"]
    }
    if not entries:
        st.info("You have no published classes to change.")
    else:
        # Outside the form so the choices below update when it changes.
        kind = st.radio(
            "What do you want to change?", ["Time", "Room"], horizontal=True
        )
        if kind == "Time":
            choices = {t["label"]: t["id"] for t in options["time_slots"]}
        else:
            choices = {
                f"{r['name']} ({r['building']}, seats {r['capacity']})": r["id"]
                for r in options["rooms"]
            }
        with st.form("new_request", clear_on_submit=True):
            course = st.selectbox("Course", list(entries))
            new_value = st.selectbox(f"New {kind.lower()}", list(choices))
            reason = st.text_area("Reason")
            submitted = st.form_submit_button("Submit request")
        if submitted:
            with ui.loading():
                try:
                    call(
                        "POST",
                        "/modifications",
                        json={
                            "entry_id": entries[course],
                            "modification_type": "slot"
                            if kind == "Time"
                            else "location",
                            "value": choices[new_value],
                            "reason": reason,
                        },
                    )
                except api_client.BackendError as exc:
                    st.error(str(exc))
                else:
                    st.success("Request submitted.")

st.subheader("Requests to review" if is_coordinator else "My requests")
if is_coordinator and st.button("View Requests"):
    with ui.loading():
        try:
            open_requests = call("GET", "/requests/open")
        except api_client.BackendError as exc:
            st.error(str(exc))
        else:
            if open_requests:
                st.table(open_requests)
            else:
                st.info("No open modification requests.")

try:
    requests_list = call("GET", "/modifications")
except api_client.BackendError as exc:
    st.error(str(exc))
    st.stop()

if not requests_list:
    st.info("No requests yet.")

for r in requests_list:
    with st.container(border=True):
        changes = []
        if r["proposed_slot"]:
            changes.append(f"time {r['current_slot']} → {r['proposed_slot']}")
        if r["proposed_room"]:
            changes.append(f"room {r['current_room']} → {r['proposed_room']}")
        who = f" (from {r['requester']})" if is_coordinator else ""
        st.markdown(
            f"**{r['course_code']}**: {', '.join(changes)} - *{r['status']}*{who}"
        )
        st.caption(f"Reason: {r['reason'] or '-'}")
        if r["reviewer_comment"]:
            st.caption(f"Coordinator: {r['reviewer_comment']}")
        if is_coordinator and r["status"] == "pending":
            comment = st.text_input(
                "Comment (optional)", key=f"comment_{r['id']}"
            )
            accept_col, decline_col = st.columns(2)
            if accept_col.button("Accept", key=f"accept_{r['id']}"):
                review(r["id"], True, comment)
            if decline_col.button("Decline", key=f"decline_{r['id']}"):
                review(r["id"], False, comment)
