"""dummy data

Revision ID: c4d9a1f07b23
Revises: e7547025d840
Create Date: 2026-10-06
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "c4d9a1f07b23"
down_revision = "e7547025d840"
branch_labels = None
depends_on = None

PASSWORD_HASH = "$2b$12$3NnzZvsVdjTC0xL7ThEdb.v2Zd2rugNJkODv5n6DWv8y3aqQhxAve"  # Password123!


def ts(month, day, hour=9):
    return datetime(2026, month, day, hour, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Lightweight table definitions. Migrations must not import the app's models,
# because the models change over time but a migration must not.
# --------------------------------------------------------------------------
# Columns that need an explicit type so values are converted correctly.
_TYPES = {
    "report": sa.JSON(),
    "created_at": sa.DateTime(timezone=True),
    "resolved_at": sa.DateTime(timezone=True),
    "is_active": sa.Boolean(),
}


def _table(name, *columns):
    return sa.table(name, *[sa.column(c, _TYPES.get(c)) for c in columns])


users = _table(
    "users",
    "id",
    "username",
    "email",
    "full_name",
    "password_hash",
    "role",
    "is_active",
    "created_at",
    "coordinator_id",
    "min_course_load",
    "max_course_load",
)
rooms = _table("rooms", "id", "name", "building", "zone", "capacity")
time_slots = _table("time_slots", "id", "hour", "label")
semesters = _table("semesters", "id", "name", "is_active")
courses = _table("courses", "id", "semester_id", "code", "name", "enrollment")
course_instructors = _table(
    "course_instructors", "course_id", "instructor_id", "preference"
)
course_pair_rules = _table(
    "course_pair_rules", "id", "course_a_id", "course_b_id", "rule_type"
)
enrollments = _table("enrollments", "student_id", "course_id")
schedules = _table(
    "schedules",
    "id",
    "semester_id",
    "created_by_id",
    "status",
    "fitness",
    "generation_found",
    "generations_run",
    "report",
    "created_at",
)
schedule_entries = _table(
    "schedule_entries",
    "id",
    "schedule_id",
    "course_id",
    "instructor_id",
    "room_id",
    "time_slot_id",
    "fitness",
)
modification_requests = _table(
    "modification_requests",
    "id",
    "schedule_entry_id",
    "requester_id",
    "assigned_to_id",
    "proposed_room_id",
    "proposed_time_slot_id",
    "reason",
    "status",
    "reviewed_by_id",
    "reviewer_comment",
    "created_at",
    "resolved_at",
)
calendar_links = _table(
    "calendar_links",
    "id",
    "user_id",
    "provider",
    "calendar_id",
    "refresh_token",
    "created_at",
)

# Tables with an auto-increment "id" (their sequences are reset on PostgreSQL).
SEQUENCE_TABLES = [
    "users",
    "rooms",
    "time_slots",
    "semesters",
    "courses",
    "course_pair_rules",
    "schedules",
    "schedule_entries",
    "modification_requests",
    "calendar_links",
]

# --------------------------------------------------------------------------
# People (ids: coordinators 1-2, instructors 3-8, students 9-20)
# --------------------------------------------------------------------------
COORDINATORS = [
    (1, "amorgan", "Dr. Ada Morgan"),
    (2, "dcho", "Prof. Daniel Cho"),
]

INSTRUCTORS = [
    (3, "praman", "Dr. Priya Raman", 1),
    (4, "mwebb", "Dr. Marcus Webb", 1),
    (5, "erossi", "Dr. Elena Rossi", 1),
    (6, "sokafor", "Dr. Samuel Okafor", 2),
    (7, "hlindqvist", "Dr. Hannah Lindqvist", 2),
    (8, "talvarez", "Dr. Tomas Alvarez", 2),
]
STUDENT_NAMES = [
    "Alex Carter",
    "Bianca Silva",
    "Chen Wei",
    "Dara Nolan",
    "Emeka Obi",
    "Farah Haddad",
    "Gustavo Reyes",
    "Hana Kobayashi",
    "Ivan Petrov",
    "Jasmine Clarke",
    "Kofi Mensah",
    "Lena Fischer",
]
STUDENTS = [  # (id, username, full name)
    (9 + i, f"student{i + 1:02d}", name) for i, name in enumerate(STUDENT_NAMES)
]

# --------------------------------------------------------------------------
# Rooms and time slots
# --------------------------------------------------------------------------
ROOMS = [  # (id, name, building, zone, capacity)
    (1, "Science 101", "Science", "Main", 120),
    (2, "Science 210", "Science", "Main", 60),
    (3, "Hall 12", "Hall", "Main", 80),
    (4, "Hall 14", "Hall", "Main", 40),
    (5, "Annex 03", "Annex", "North", 30),
    (6, "Annex 05", "Annex", "North", 24),
]
SLOTS = [  # (id, hour, label)
    (1, 9, "9AM"),
    (2, 10, "10AM"),
    (3, 11, "11AM"),
    (4, 12, "12PM"),
    (5, 13, "1PM"),
    (6, 14, "2PM"),
    (7, 15, "3PM"),
]

# --------------------------------------------------------------------------
# Semester and courses (id, code, title, expected enrollment)
# --------------------------------------------------------------------------
SEMESTER_ID = 1
COURSES = [
    (1, "CS101A", "Intro to Programming (Section A)", 40),
    (2, "CS101B", "Intro to Programming (Section B)", 35),
    (3, "CS201", "Data Structures", 50),
    (4, "CS230", "Databases", 30),
    (5, "CS310", "Algorithms", 45),
    (6, "CS350", "Software Engineering", 25),
    (7, "MATH120", "Discrete Mathematics", 90),
    (8, "MATH220", "Linear Algebra", 55),
]
COURSE_ID = {code: cid for cid, code, _, _ in COURSES}
INSTRUCTOR_ID = {username: iid for iid, username, _, _ in INSTRUCTORS}

# Who can teach what: username -> (preferred course codes, qualified codes)
TEACHING = {
    "praman": (["CS101A", "CS101B", "CS201"], ["CS230"]),
    "mwebb": (["CS230", "CS350"], ["CS201", "CS310"]),
    "erossi": (["CS310", "CS201"], ["CS101A", "CS101B"]),
    "sokafor": (["MATH120", "MATH220"], ["CS310"]),
    "hlindqvist": (["MATH120"], ["MATH220", "CS230"]),
    "talvarez": (["CS350", "CS230"], ["CS101B"]),
}

# Rules between two courses: sections should be far apart in the day (spread),
# courses students take together should be close (related).
PAIR_RULES = [
    (1, "CS101A", "CS101B", "spread"),
    (2, "CS101A", "MATH120", "related"),
    (3, "CS101B", "MATH120", "related"),
    (4, "CS201", "MATH220", "related"),
]

# Which courses each sample student takes (student number 1-12).
ENROLLMENT = {
    1: ["CS101A", "MATH120"],
    2: ["CS101A", "MATH120"],
    3: ["CS101A", "MATH120"],
    4: ["CS101B", "MATH120"],
    5: ["CS101B", "MATH120"],
    6: ["CS101B", "MATH220"],
    7: ["CS201", "CS230", "MATH220"],
    8: ["CS201", "CS230", "MATH220"],
    9: ["CS201", "CS230", "CS350"],
    10: ["CS310", "CS350", "MATH220"],
    11: ["CS310", "CS350"],
    12: ["CS201", "CS310", "CS350"],
}

# --------------------------------------------------------------------------
# Schedules. Entry: (course code, instructor username, room id, slot id,
# fitness). Schedule 1 is an earlier draft; schedule 2 is the published one.
# --------------------------------------------------------------------------
DRAFT_ENTRIES = [
    ("CS101A", "praman", 4, 1, 2.1),
    ("CS101B", "erossi", 4, 5, 1.6),
    ("CS201", "praman", 2, 2, 2.3),
    ("CS230", "mwebb", 5, 3, 2.0),
    ("CS310", "erossi", 2, 6, 1.9),
    ("CS350", "talvarez", 5, 4, 2.0),
    ("MATH120", "sokafor", 1, 3, 1.8),
    ("MATH220", "hlindqvist", 2, 3, 1.4),
]
PUBLISHED_ENTRIES = [
    ("CS101A", "praman", 4, 1, 2.4),
    ("CS101B", "praman", 4, 7, 2.2),
    ("CS201", "praman", 2, 2, 2.5),
    ("CS230", "talvarez", 5, 3, 2.3),
    ("CS310", "erossi", 2, 3, 2.4),
    ("CS350", "mwebb", 5, 4, 2.5),
    ("MATH120", "sokafor", 1, 3, 2.2),
    ("MATH220", "hlindqvist", 2, 5, 1.8),
]
SCHEDULES = [  # (id, status, created at, generation found, entries)
    (1, "draft", ts(10, 1), 37, DRAFT_ENTRIES),
    (2, "published", ts(10, 3), 61, PUBLISHED_ENTRIES),
]
# Entry ids: schedule 1 -> 1..8, schedule 2 -> 9..16 (in the order above).
PUBLISHED_ENTRY_ID = {
    code: 8 + i for i, (code, *_rest) in enumerate(PUBLISHED_ENTRIES, start=1)
}

# --------------------------------------------------------------------------
# Modification requests on the published schedule.
# --------------------------------------------------------------------------
REQUESTS = [
    {
        "id": 1,
        "course": "CS101B",
        "requester": "praman",
        "room": None,
        "slot": 3,
        "status": "pending",
        "reason": "I hold office hours at 3PM. Could this section move to "
        "11AM?",
        "created": ts(10, 4),
    },
    {
        "id": 2,
        "course": "CS350",
        "requester": "mwebb",
        "room": 4,
        "slot": None,
        "status": "pending",
        "reason": "Group project presentations need a larger room.",
        "created": ts(10, 4, 14),
    },
    {
        "id": 3,
        "course": "MATH120",
        "requester": "sokafor",
        "room": None,
        "slot": 3,
        "status": "accepted",
        "reason": "Conflicts with a department meeting at 10AM.",
        "created": ts(10, 3, 16),
        "reviewer": "dcho",
        "comment": "Approved. The room is free at 11AM.",
        "resolved": ts(10, 4, 10),
    },
    {
        "id": 4,
        "course": "MATH220",
        "requester": "hlindqvist",
        "room": None,
        "slot": 2,
        "status": "declined",
        "reason": "I would prefer to teach in the morning.",
        "created": ts(10, 3, 17),
        "reviewer": "dcho",
        "comment": "Declined: Science 210 is already booked at 10AM.",
        "resolved": ts(10, 4, 11),
    },
]

CALENDAR_LINKS = [  # (id, username, calendar id)
    (1, "praman", "praman@example.com"),
    (2, "student01", "student01@example.com"),
]


def _user_ids():
    ids = {username: uid for uid, username, _ in COORDINATORS}
    ids.update({username: uid for uid, username, _, _ in INSTRUCTORS})
    ids.update({username: uid for uid, username, _ in STUDENTS})
    return ids


def _assert_tables_empty():
    """Refuses to run on a database that already holds data (ids would clash)."""
    bind = op.get_bind()
    for table in ("users", "rooms", "time_slots", "semesters"):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if count:
            raise RuntimeError(
                f"Cannot load dummy data: table '{table}' already has rows. "
                "Use an empty database (for example a new Neon branch), or "
                "delete the existing rows first."
            )


def upgrade() -> None:
    _assert_tables_empty()
    user_id = _user_ids()

    def user_row(uid, username, full_name, role, coordinator_id=None):
        return {
            "id": uid,
            "username": username,
            "email": f"{username}@example.com",
            "full_name": full_name,
            "password_hash": PASSWORD_HASH,
            "role": role,
            "is_active": True,
            "created_at": ts(9, 1),
            "coordinator_id": coordinator_id,
            "min_course_load": 1,
            "max_course_load": 3,
        }

    # Coordinators first: instructors point at them.
    op.bulk_insert(
        users,
        [user_row(i, u, n, "coordinator") for i, u, n in COORDINATORS],
    )
    op.bulk_insert(
        users,
        [user_row(i, u, n, "instructor", c) for i, u, n, c in INSTRUCTORS]
        + [user_row(i, u, n, "student") for i, u, n in STUDENTS],
    )

    op.bulk_insert(
        rooms,
        [
            {"id": i, "name": n, "building": b, "zone": z, "capacity": c}
            for i, n, b, z, c in ROOMS
        ],
    )
    op.bulk_insert(
        time_slots, [{"id": i, "hour": h, "label": lb} for i, h, lb in SLOTS]
    )
    op.bulk_insert(
        semesters,
        [{"id": SEMESTER_ID, "name": "Spring 2027", "is_active": True}],
    )
    op.bulk_insert(
        courses,
        [
            {
                "id": i,
                "semester_id": SEMESTER_ID,
                "code": code,
                "name": title,
                "enrollment": n,
            }
            for i, code, title, n in COURSES
        ],
    )

    preferences = []
    for username, (preferred, qualified) in TEACHING.items():
        for codes, kind in ((preferred, "preferred"), (qualified, "qualified")):
            for code in codes:
                preferences.append(
                    {
                        "course_id": COURSE_ID[code],
                        "instructor_id": INSTRUCTOR_ID[username],
                        "preference": kind,
                    }
                )
    op.bulk_insert(course_instructors, preferences)

    op.bulk_insert(
        course_pair_rules,
        [
            {
                "id": i,
                "course_a_id": COURSE_ID[a],
                "course_b_id": COURSE_ID[b],
                "rule_type": kind,
            }
            for i, a, b, kind in PAIR_RULES
        ],
    )
    op.bulk_insert(
        enrollments,
        [
            {"student_id": STUDENTS[n - 1][0], "course_id": COURSE_ID[code]}
            for n, codes in ENROLLMENT.items()
            for code in codes
        ],
    )

    entry_rows = []
    entry_id = 0
    for sid, _status, _created, _found, entries in SCHEDULES:
        for code, username, room_id, slot_id, fitness in entries:
            entry_id += 1
            entry_rows.append(
                {
                    "id": entry_id,
                    "schedule_id": sid,
                    "course_id": COURSE_ID[code],
                    "instructor_id": INSTRUCTOR_ID[username],
                    "room_id": room_id,
                    "time_slot_id": slot_id,
                    "fitness": fitness,
                }
            )
    op.bulk_insert(
        schedules,
        [
            {
                "id": sid,
                "semester_id": SEMESTER_ID,
                "created_by_id": 1,
                "status": status,
                "fitness": round(sum(e[4] for e in entries), 2),
                "generation_found": found,
                "generations_run": 100,
                "report": {"soft_violations": [], "history": []},
                "created_at": created,
            }
            for sid, status, created, found, entries in SCHEDULES
        ],
    )
    op.bulk_insert(schedule_entries, entry_rows)

    coordinator_of = {u: c for _, u, _, c in INSTRUCTORS}
    op.bulk_insert(
        modification_requests,
        [
            {
                "id": r["id"],
                "schedule_entry_id": PUBLISHED_ENTRY_ID[r["course"]],
                "requester_id": user_id[r["requester"]],
                "assigned_to_id": coordinator_of[r["requester"]],
                "proposed_room_id": r["room"],
                "proposed_time_slot_id": r["slot"],
                "reason": r["reason"],
                "status": r["status"],
                "reviewed_by_id": user_id[r["reviewer"]]
                if "reviewer" in r
                else None,
                "reviewer_comment": r.get("comment"),
                "created_at": r["created"],
                "resolved_at": r.get("resolved"),
            }
            for r in REQUESTS
        ],
    )
    op.bulk_insert(
        calendar_links,
        [
            {
                "id": i,
                "user_id": user_id[username],
                "provider": "google",
                "calendar_id": cal,
                "refresh_token": None,
                "created_at": ts(9, 15),
            }
            for i, username, cal in CALENDAR_LINKS
        ],
    )

    # Rows were inserted with explicit ids, so tell PostgreSQL where to carry
    # on counting; otherwise the first new row the app creates would clash.
    if op.get_bind().dialect.name == "postgresql":
        for table in SEQUENCE_TABLES:
            op.execute(
                sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT MAX(id) FROM {table}))"
                )
            )


def downgrade() -> None:
    """Removes exactly the rows inserted above, and nothing else."""
    ids = lambda rows: [r[0] for r in rows]  # noqa: E731
    op.execute(
        modification_requests.delete().where(
            modification_requests.c.id.in_([r["id"] for r in REQUESTS])
        )
    )
    op.execute(
        calendar_links.delete().where(
            calendar_links.c.id.in_(ids(CALENDAR_LINKS))
        )
    )
    op.execute(
        enrollments.delete().where(enrollments.c.course_id.in_(ids(COURSES)))
    )
    op.execute(
        schedule_entries.delete().where(
            schedule_entries.c.schedule_id.in_(ids(SCHEDULES))
        )
    )
    op.execute(schedules.delete().where(schedules.c.id.in_(ids(SCHEDULES))))
    op.execute(
        course_pair_rules.delete().where(
            course_pair_rules.c.id.in_(ids(PAIR_RULES))
        )
    )
    op.execute(
        course_instructors.delete().where(
            course_instructors.c.course_id.in_(ids(COURSES))
        )
    )
    op.execute(courses.delete().where(courses.c.id.in_(ids(COURSES))))
    op.execute(semesters.delete().where(semesters.c.id == SEMESTER_ID))
    op.execute(time_slots.delete().where(time_slots.c.id.in_(ids(SLOTS))))
    op.execute(rooms.delete().where(rooms.c.id.in_(ids(ROOMS))))
    # Instructors and students first, because instructors reference coordinators.
    op.execute(
        users.delete().where(users.c.id.in_(ids(INSTRUCTORS) + ids(STUDENTS)))
    )
    op.execute(users.delete().where(users.c.id.in_(ids(COORDINATORS))))
