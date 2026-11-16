"""User management page (coordinators only)."""

import streamlit as st

import api_client
import auth
import ui

ROLES = ["student", "instructor", "coordinator"]
FLASH_KEY = "users_flash"
ADD_FORM_VERSION_KEY = "users_add_form_version"
TABLE_VERSION_KEY = "users_table_version"
SELECTED_KEY = "users_selected_id"
SELECTING_TABLE_KEY = "users_selecting_table"
DIALOG_CLOSED_KEY = "users_dialog_closed"


@st.cache_data(ttl=60, show_spinner=False)
def fetch(path: str, token: str, params: tuple = ()) -> list[dict]:
    """GET from the backend, cached briefly so clicks don't refetch."""
    return api_client.request("GET", path, token=token, params=dict(params))


def get(path: str, **params: object) -> list[dict]:
    return fetch(path, auth.get_token(), tuple(sorted(params.items())))


def change(method: str, path: str, body: dict, success: str) -> None:
    """Send a change; on success show `success` and reload the page data."""
    with ui.loading():
        try:
            api_client.request(method, path, token=auth.get_token(), json=body)
        except api_client.BackendError as exc:
            if exc.status_code in (400, 404, 409, 422):
                lines = exc.detail.replace("\n", "\n\n")
                st.error(f"Could not save:\n\n{lines}")
            else:
                st.error(str(exc))
            return
    fetch.clear()
    st.session_state[FLASH_KEY] = success
    # Saving can reorder the table, so start a fresh table and keep the
    # selected user by id.
    st.session_state[TABLE_VERSION_KEY] = (
        st.session_state.get(TABLE_VERSION_KEY, 0) + 1
    )
    st.rerun()


@st.dialog("Confirm changes")
def confirm_change(
    user: dict, body: dict, success: str, risks: list[str]
) -> None:
    st.write(f"These changes to {user['full_name']} need confirming:")
    st.markdown("\n".join(f"- {risk}" for risk in risks))
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel"):
        st.session_state[DIALOG_CLOSED_KEY] = True
        st.rerun()
    if confirm.button("Confirm", type="primary"):
        st.session_state[DIALOG_CLOSED_KEY] = True
        change("PATCH", f"/users/{user['id']}", body, success)
        st.session_state.pop(DIALOG_CLOSED_KEY, None)  # Saving failed.


def course_label(course: dict) -> str:
    return f"{course['code']} - {course['name']}"


def coordinator_options() -> dict[int | None, str]:
    coordinators = get("/users", role="coordinator", include_inactive=False)
    return {None: "No coordinator"} | {
        c["id"]: c["full_name"] for c in coordinators
    }


def edit_details(user: dict) -> None:
    is_me = user["id"] == auth.current_user()["id"]
    is_instructor = user["role"] == "instructor"
    coordinators = coordinator_options() if is_instructor else {}

    with st.form(f"details-{user['id']}"):
        full_name = st.text_input("Full name", user["full_name"])
        email = st.text_input("Email", user["email"])
        role = st.selectbox(
            "Role",
            ROLES,
            index=ROLES.index(user["role"]),
            format_func=str.title,
            disabled=is_me,
        )
        is_active = st.toggle(
            "Active (can log in)", value=user["is_active"], disabled=is_me
        )
        body = {
            "full_name": full_name,
            "email": email,
            "role": role,
            "is_active": is_active,
        }
        if is_instructor:
            current = user["coordinator_id"]
            options = list(coordinators)
            body["coordinator_id"] = st.selectbox(
                "Coordinator (receives their change requests)",
                options,
                index=options.index(current) if current in options else 0,
                format_func=coordinators.get,
            )
            low, high = st.columns(2)
            body["min_course_load"] = low.number_input(
                "Minimum courses", 0, 10, user["min_course_load"]
            )
            body["max_course_load"] = high.number_input(
                "Maximum courses", 0, 10, user["max_course_load"]
            )
        if is_me:
            st.caption("You can't change your own role or deactivate yourself.")
        submitted = st.form_submit_button("Save changes", type="primary")

    # The rerun that closes the dialog still reports the form as submitted.
    dialog_closed = st.session_state.pop(DIALOG_CLOSED_KEY, False)
    if submitted and not dialog_closed:
        success = f"Changes saved for {full_name}"
        risks = []
        if role != user["role"]:
            risks.append(
                f"Change role from {user['role'].title()} to {role.title()}. "
                "Course links that no longer apply are removed."
            )
        if user["is_active"] and not is_active:
            risks.append(
                "Deactivate the account. They will not be able to log in."
            )
        if risks:
            confirm_change(user, body, success, risks)
        else:
            change("PATCH", f"/users/{user['id']}", body, success)
    st.caption(
        "Changing a role removes course links that no longer apply. "
        "Deactivated users can't log in; anyone already logged in is signed "
        "out when their session ends (within 10 minutes)."
    )


def reset_password(user: dict) -> None:
    with st.expander("Reset password"):
        with st.form(f"password-{user['id']}", clear_on_submit=True):
            password = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Set password"):
                if password != confirm:
                    st.error("Passwords do not match.")
                else:
                    change(
                        "PUT",
                        f"/users/{user['id']}/password",
                        {"password": password},
                        f"Password reset for {user['username']}.",
                    )


def assign_courses(user: dict) -> None:
    st.markdown("#### Courses")
    semesters = {s["id"]: s for s in get("/semesters")}
    if not semesters:
        st.info("No semesters exist yet.")
        return
    semester_id = st.selectbox(
        "Semester",
        list(semesters),
        format_func=lambda sid: (
            semesters[sid]["name"]
            + ("" if semesters[sid]["is_active"] else " (inactive)")
        ),
        key=f"semester-{user['id']}",
    )
    courses = {c["id"]: c for c in get(f"/semesters/{semester_id}/courses")}
    if not courses:
        st.info("This semester has no courses yet.")
        return
    links = [
        link
        for link in get(f"/users/{user['id']}/courses")
        if link["semester_id"] == semester_id
    ]

    def current(relation: str) -> list[int]:
        return [
            link["course_id"] for link in links if link["relation"] == relation
        ]

    def label(course_id: int) -> str:
        return course_label(courses[course_id])

    with st.form(f"courses-{user['id']}-{semester_id}"):
        if user["role"] == "student":
            enrolled = st.multiselect(
                "Enrolled in", list(courses), current("enrolled"), label
            )
            body = {"semester_id": semester_id, "course_ids": enrolled}
            path = f"/users/{user['id']}/enrollments"
        else:
            preferred = st.multiselect(
                "Prefers to teach", list(courses), current("preferred"), label
            )
            qualified = st.multiselect(
                "Qualified to teach", list(courses), current("qualified"), label
            )
            st.caption(
                "The scheduler gives preferred courses first; qualified "
                "courses are acceptable but not the first choice."
            )
            body = {
                "semester_id": semester_id,
                "preferred": preferred,
                "qualified": qualified,
            }
            path = f"/users/{user['id']}/teaching"
        if st.form_submit_button("Save courses", type="primary"):
            semester = semesters[semester_id]["name"]
            change("PUT", path, body, f"Saved {semester} courses.")


def manage_users() -> None:
    role_col, search_col, inactive_col = st.columns([1, 2, 1])
    role = role_col.selectbox(
        "Filter by role", ["all", *ROLES], format_func=str.title
    )
    search = search_col.text_input(
        "Search", placeholder="Name, username or email"
    )
    with inactive_col:
        st.write("")  # Line the toggle up with the inputs beside it.
        show_inactive = st.toggle("Show inactive", value=True)

    params = {"search": search, "include_inactive": show_inactive}
    if role != "all":
        params["role"] = role
    with ui.loading():
        users = {u["id"]: u for u in get("/users", **params)}
    if not users:
        st.info("No users match.")
        return

    version = st.session_state.get(TABLE_VERSION_KEY, 0)
    table_key = f"users-table-{version}-{role}-{search}-{show_inactive}"
    event = st.dataframe(
        [
            {
                "Name": u["full_name"],
                "Username": u["username"],
                "Email": u["email"],
                "Role": u["role"].title(),
                "Active": u["is_active"],
                "Coordinator": u["coordinator_name"] or "",
                "Courses": ", ".join(u["courses"]),
            }
            for u in users.values()
        ],
        hide_index=True,
        width="stretch",
        key=table_key,
        on_select="rerun",
        selection_mode="single-row",
    )

    rows = event.selection.rows
    if rows:
        st.session_state[SELECTED_KEY] = list(users)[rows[0]]
        st.session_state[SELECTING_TABLE_KEY] = table_key
    elif st.session_state.get(SELECTING_TABLE_KEY) == table_key:
        # The row was clicked again to clear the selection.
        st.session_state.pop(SELECTED_KEY, None)
        st.session_state.pop(SELECTING_TABLE_KEY, None)

    user_id = st.session_state.get(SELECTED_KEY)
    if user_id not in users:
        st.caption("Select a user in the table to edit them.")
        return
    user = users[user_id]
    with st.container(border=True):
        st.subheader(f"{user['full_name']} ({user['username']})")
        if not user["is_active"]:
            st.warning("This account is deactivated. They cannot log in.")
        edit_details(user)
        reset_password(user)
        if user["role"] in ("student", "instructor"):
            assign_courses(user)


def add_user() -> None:
    role = st.selectbox(
        "Role", ROLES, format_func=str.title, key="new-user-role"
    )
    version = st.session_state.setdefault(ADD_FORM_VERSION_KEY, 0)
    with st.form(f"add-user-{version}"):
        full_name = st.text_input("Full name")
        username = st.text_input(
            "Username", help="3-50 letters, digits, dots or underscores."
        )
        email = st.text_input("Email")
        password = st.text_input(
            "Temporary password",
            type="password",
            help="At least 8 characters. Share it with the user privately.",
        )
        confirm = st.text_input("Confirm password", type="password")
        body = {
            "full_name": full_name,
            "username": username,
            "email": email,
            "password": password,
            "role": role,
        }
        if role == "instructor":
            coordinators = coordinator_options()
            body["coordinator_id"] = st.selectbox(
                "Coordinator",
                list(coordinators),
                format_func=coordinators.get,
            )
            low, high = st.columns(2)
            body["min_course_load"] = low.number_input(
                "Minimum courses", 0, 10, 3
            )
            body["max_course_load"] = high.number_input(
                "Maximum courses", 0, 10, 4
            )
        submitted = st.form_submit_button("Add user", type="primary")

    if submitted:
        if not all(
            value.strip() for value in (full_name, username, email, password)
        ):
            st.error("Please enter valid information:\n\nFill in every field.")
        elif password != confirm:
            st.error(
                "Please enter valid information:\n\nPasswords do not match."
            )
        else:
            st.session_state[ADD_FORM_VERSION_KEY] = version + 1
            change("POST", "/users", body, f"Added {role} {username.strip()}.")
            # Only reached on error: keep what was typed.
            st.session_state[ADD_FORM_VERSION_KEY] = version


st.title("Users")
flash = st.session_state.pop(FLASH_KEY, None)
if flash:
    st.success(flash)

manage_tab, add_tab = st.tabs(["Manage users", "Add user"])
with manage_tab:
    manage_users()
with add_tab:
    add_user()
