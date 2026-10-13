import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.modifications as mods
from app.models import ModificationRequest

COORD_A, COORD_B, PRAMAN, MWEBB, LINDQVIST, ORPHAN = 1, 2, 3, 4, 5, 6
E_CS101, E_CS201, E_CS350, E_MATH120, E_CS450 = 1, 2, 3, 4, 5


# Database fixture
class Db:
    def __init__(self, session_factory):
        self.Session = session_factory

    def run(self, sql, rows=None, **params):
        with self.Session() as s:
            s.execute(text(sql), rows if rows is not None else params)
            s.commit()

    def rows(self, sql, **params):
        with self.Session() as s:
            return s.execute(text(sql), params).all()

    def place(self, entry_id):
        """(room_id, time_slot_id, instructor_id) of a schedule entry."""
        row = self.rows(
            "SELECT room_id, time_slot_id, instructor_id FROM schedule_entries WHERE id = :id",
            id=entry_id,
        )[0]
        return tuple(row)

    def request_rows(self):
        return self.rows("SELECT * FROM modification_requests")


def _seed(d):
    created = "2026-09-01 09:00:00"
    d.run(
        "INSERT INTO users (id, username, email, full_name, password_hash, role, is_active, "
        "created_at, coordinator_id, min_course_load, max_course_load) VALUES "
        "(:id, :u, :e, :n, 'x', :role, 1, :created, :coord, 1, 3)",
        rows=[
            dict(
                id=1,
                u="coordA",
                e="a@x.com",
                n="Coord A",
                role="coordinator",
                created=created,
                coord=None,
            ),
            dict(
                id=2,
                u="coordB",
                e="b@x.com",
                n="Coord B",
                role="coordinator",
                created=created,
                coord=None,
            ),
            dict(
                id=3,
                u="praman",
                e="p@x.com",
                n="Praman",
                role="instructor",
                created=created,
                coord=1,
            ),
            dict(
                id=4,
                u="mwebb",
                e="m@x.com",
                n="Mwebb",
                role="instructor",
                created=created,
                coord=1,
            ),
            dict(
                id=5,
                u="lind",
                e="l@x.com",
                n="Lindqvist",
                role="instructor",
                created=created,
                coord=2,
            ),
            dict(
                id=6,
                u="orphan",
                e="o@x.com",
                n="Orphan",
                role="instructor",
                created=created,
                coord=None,
            ),
        ],
    )
    d.run(
        "INSERT INTO rooms (id, name, building, zone, capacity) VALUES (:id, :n, 'B', :z, :c)",
        rows=[
            dict(id=1, n="Big", z="Main", c=120),
            dict(id=2, n="Mid", z="Main", c=60),
            dict(id=3, n="Small", z="North", c=30),
        ],
    )
    d.run(
        "INSERT INTO time_slots (id, hour, label) VALUES (:id, :h, :l)",
        rows=[dict(id=i, h=8 + i, l=f"{8 + i}h") for i in (1, 2, 3, 4)],
    )
    d.run("INSERT INTO semesters (id, name, is_active) VALUES (1, 'Spring', 1)")
    d.run(
        "INSERT INTO courses (id, semester_id, code, name, enrollment) VALUES (:id, 1, :c, :c, :n)",
        rows=[
            dict(id=1, c="CS101", n=40),
            dict(id=2, c="CS201", n=50),
            dict(id=3, c="CS350", n=25),
            dict(id=4, c="MATH120", n=90),
            dict(id=5, c="CS450", n=20),
        ],
    )
    d.run(
        "INSERT INTO course_instructors (course_id, instructor_id, preference) VALUES (:c, :i, 'preferred')",
        rows=[
            dict(c=1, i=PRAMAN),
            dict(c=1, i=MWEBB),
            dict(c=2, i=PRAMAN),
            dict(c=2, i=MWEBB),
            dict(c=3, i=MWEBB),
            dict(c=3, i=LINDQVIST),
            dict(c=4, i=LINDQVIST),
            dict(c=5, i=ORPHAN),
        ],
    )
    d.run(
        "INSERT INTO schedules (id, semester_id, status, fitness, generation_found, generations_run, created_at) "
        "VALUES (1, 1, 'published', 0, 1, 1, :created)",
        created=created,
    )
    d.run(
        "INSERT INTO schedule_entries (id, schedule_id, course_id, instructor_id, room_id, time_slot_id, fitness) "
        "VALUES (:id, 1, :c, :i, :r, :s, 0)",
        rows=[
            dict(id=1, c=1, i=PRAMAN, r=1, s=1),
            dict(id=2, c=2, i=PRAMAN, r=2, s=2),
            dict(id=3, c=3, i=MWEBB, r=3, s=1),
            dict(id=4, c=4, i=LINDQVIST, r=1, s=3),
            dict(id=5, c=5, i=ORPHAN, r=3, s=3),
        ],
    )


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    ModificationRequest.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(mods, "SessionLocal", session_factory)
    d = Db(session_factory)
    _seed(d)
    yield d
    engine.dispose()


def status_of(request):
    return getattr(request.status, "value", request.status)


# Lookups
def test_get_instructor_from_schedule(db):
    assert mods.get_instructor_from_schedule(E_CS201).id == PRAMAN


def test_get_instructor_from_unknown_entry_raises(db):
    with pytest.raises(ValueError, match="No schedule entry found with ID 999"):
        mods.get_instructor_from_schedule(999)


def test_get_coordinator_from_instructor(db):
    assert mods.get_coordinator_from_instructor(PRAMAN).id == COORD_A
    assert mods.get_coordinator_from_instructor(LINDQVIST).id == COORD_B


def test_instructor_without_a_coordinator_raises_a_clear_error(db):
    with pytest.raises(ValueError, match="has no coordinator"):
        mods.get_coordinator_from_instructor(ORPHAN)


def test_get_coordinator_from_unknown_instructor_raises(db):
    with pytest.raises(ValueError, match="No instructor found with ID 999"):
        mods.get_coordinator_from_instructor(999)


def test_get_coordinator_from_schedule(db):
    assert mods.get_coordinator_from_schedule(E_CS101).id == COORD_A
    assert mods.get_coordinator_from_schedule(E_MATH120).id == COORD_B


def test_get_coordinator_from_schedule_without_coordinator_raises(db):
    with pytest.raises(ValueError, match="has no coordinator"):
        mods.get_coordinator_from_schedule(E_CS450)


def test_get_coordinator_from_unknown_entry_raises(db):
    with pytest.raises(ValueError, match="No schedule entry found"):
        mods.get_coordinator_from_schedule(999)


# modify_schedule: valid changes
def test_modify_slot_updates_only_the_time_slot(db):
    mods.modify_schedule(E_CS101, "slot", 4)
    assert db.place(E_CS101) == (1, 4, PRAMAN)


def test_modify_location_updates_only_the_room(db):
    mods.modify_schedule(E_CS101, "location", 2)
    assert db.place(E_CS101) == (2, 1, PRAMAN)


def test_modify_instructor_updates_only_the_instructor(db):
    mods.modify_schedule(E_CS201, "instructor", MWEBB)
    assert db.place(E_CS201) == (2, 2, MWEBB)


def test_modifying_one_entry_leaves_the_others_alone(db):
    before = {e: db.place(e) for e in (E_CS201, E_CS350, E_MATH120, E_CS450)}
    mods.modify_schedule(E_CS101, "slot", 4)
    assert {e: db.place(e) for e in before} == before


def test_entries_in_other_schedules_are_not_clashes(db):
    db.run(
        "INSERT INTO schedules (id, semester_id, status, fitness, generation_found, generations_run, "
        "created_at) VALUES (2, 1, 'draft', 0, 1, 1, '2026-09-02 09:00:00')"
    )
    db.run(
        "INSERT INTO schedule_entries (id, schedule_id, course_id, instructor_id, room_id, time_slot_id, "
        "fitness) VALUES (10, 2, 1, :p, 1, 4, 0)",
        p=PRAMAN,
    )  # same room, slot and instructor, other schedule
    mods.modify_schedule(E_CS101, "slot", 4)
    assert db.place(E_CS101) == (1, 4, PRAMAN)


# modify_schedule: rejected changes (nothing may be written)
@pytest.mark.parametrize(
    "entry, kind, value, message",
    [
        (E_CS101, "colour", 1, "Invalid modification type: colour"),
        (999, "slot", 1, "No schedule entry found with ID 999"),
        (E_CS101, "slot", 99, "No time slot found with ID 99"),
        (E_CS101, "location", 99, "No room found with ID 99"),
        (E_CS101, "location", 3, "too small"),  # 40 students, capacity 30
        (
            E_CS350,
            "location",
            1,
            "room is already booked",
        ),  # room 1 is used at slot 1 by entry 1
        (
            E_CS101,
            "slot",
            2,
            "instructor already teaches",
        ),  # Praman teaches entry 2 at slot 2
        (
            E_CS101,
            "instructor",
            MWEBB,
            "instructor already teaches",
        ),  # Mwebb teaches entry 3 at slot 1
        (
            E_CS350,
            "instructor",
            PRAMAN,
            "not linked to course",
        ),  # Praman isn't linked to CS350
    ],
)
def test_invalid_modifications_raise_and_change_nothing(
    db, entry, kind, value, message
):
    before = {e: db.place(e) for e in range(1, 6)}
    with pytest.raises(ValueError, match=message):
        mods.modify_schedule(entry, kind, value)
    assert {e: db.place(e) for e in before} == before


# request_modification
def test_slot_request_is_created_pending_and_routed_to_the_coordinator(db):
    req = mods.request_modification(
        E_CS101, "slot", 4, "Office hours", requester_id=PRAMAN
    )
    assert req.id is not None
    assert req.schedule_entry_id == E_CS101
    assert req.requester_id == PRAMAN
    assert req.assigned_to_id == COORD_A
    assert req.proposed_time_slot_id == 4 and req.proposed_room_id is None
    assert req.reason == "Office hours"
    assert status_of(req) == "pending"
    assert req.created_at is not None and req.resolved_at is None
    assert len(db.request_rows()) == 1


def test_location_request_proposes_a_room(db):
    req = mods.request_modification(E_CS101, "location", 2, requester_id=PRAMAN)
    assert req.proposed_room_id == 2 and req.proposed_time_slot_id is None
    assert req.reason == ""  # reason is optional


def test_requesting_does_not_change_the_schedule(db):
    mods.request_modification(E_CS101, "slot", 4, requester_id=PRAMAN)
    assert db.place(E_CS101) == (1, 1, PRAMAN)


def test_request_from_an_instructor_without_a_coordinator_is_unassigned(db):
    req = mods.request_modification(E_CS450, "slot", 4, requester_id=ORPHAN)
    assert req.assigned_to_id is None


def test_requester_id_is_required():
    with pytest.raises(TypeError):
        mods.request_modification(E_CS101, "slot", 4, "reason")


@pytest.mark.parametrize(
    "entry, kind, value, requester, error, message",
    [
        (
            E_CS101,
            "instructor",
            MWEBB,
            PRAMAN,
            ValueError,
            "Instructor changes can't be requested",
        ),
        (E_CS101, "colour", 1, PRAMAN, ValueError, "Invalid modification type"),
        (999, "slot", 4, PRAMAN, ValueError, "No schedule entry found"),
        (
            E_CS101,
            "slot",
            4,
            MWEBB,
            PermissionError,
            "Only the instructor teaching",
        ),  # not their course
        (
            E_CS101,
            "slot",
            4,
            COORD_A,
            PermissionError,
            "Only the instructor teaching",
        ),
        (E_CS101, "slot", 99, PRAMAN, ValueError, "No slot found with ID 99"),
        (
            E_CS101,
            "location",
            99,
            PRAMAN,
            ValueError,
            "No location found with ID 99",
        ),
    ],
)
def test_invalid_requests_are_rejected_and_nothing_is_stored(
    db, entry, kind, value, requester, error, message
):
    with pytest.raises(error, match=message):
        mods.request_modification(entry, kind, value, requester_id=requester)
    assert db.request_rows() == []


# review_modification: accepting
def make_request(kind="slot", value=4, entry=E_CS101, requester=PRAMAN):
    return mods.request_modification(
        entry, kind, value, "because", requester_id=requester
    )


def test_accepting_applies_the_change_and_closes_the_request(db):
    req = make_request("slot", 4)
    done = mods.review_modification(req.id, COORD_A, True, "Approved")
    assert db.place(E_CS101) == (1, 4, PRAMAN)
    assert status_of(done) == "accepted"
    assert done.reviewed_by_id == COORD_A
    assert done.reviewer_comment == "Approved"
    assert done.resolved_at is not None
    stored = db.request_rows()[0]
    assert stored.status == "accepted" and stored.reviewed_by_id == COORD_A


def test_accepting_a_room_request_changes_the_room(db):
    req = make_request("location", 2)
    mods.review_modification(req.id, COORD_A, True)
    assert db.place(E_CS101) == (2, 1, PRAMAN)


def test_a_request_with_both_a_room_and_a_slot_is_validated_as_a_whole(db):
    req = make_request("location", 1, entry=E_CS350, requester=MWEBB)
    db.run(
        "UPDATE modification_requests SET proposed_time_slot_id = 4 WHERE id = :id",
        id=req.id,
    )
    mods.review_modification(req.id, COORD_A, True)
    assert db.place(E_CS350) == (1, 4, MWEBB)


def test_any_coordinator_may_review_an_unassigned_request(db):
    req = make_request("slot", 4, entry=E_CS450, requester=ORPHAN)
    done = mods.review_modification(req.id, COORD_B, True)
    assert status_of(done) == "accepted" and done.reviewed_by_id == COORD_B
    assert db.place(E_CS450) == (3, 4, ORPHAN)


def test_accepting_a_change_that_became_invalid_rolls_everything_back(db):
    req = make_request("slot", 4)  # valid when requested...
    mods.modify_schedule(
        E_MATH120, "slot", 4
    )  # ...then MATH120 takes room 1 at slot 4
    with pytest.raises(ValueError, match="room is already booked"):
        mods.review_modification(req.id, COORD_A, True)
    assert db.place(E_CS101) == (1, 1, PRAMAN)  # schedule untouched
    stored = db.request_rows()[0]
    assert (
        stored.status == "pending"
        and stored.resolved_at is None
        and stored.reviewed_by_id is None
    )


def test_accepting_a_request_with_no_proposed_change_raises(db):
    req = make_request("slot", 4)
    db.run(
        "UPDATE modification_requests SET proposed_time_slot_id = NULL WHERE id = :id",
        id=req.id,
    )
    with pytest.raises(ValueError, match="no proposed change"):
        mods.review_modification(req.id, COORD_A, True)
    assert db.request_rows()[0].status == "pending"


# review_modification: declining
def test_declining_closes_the_request_without_touching_the_schedule(db):
    req = make_request("slot", 4)
    done = mods.review_modification(req.id, COORD_A, False, "Room is needed")
    assert status_of(done) == "declined"
    assert done.reviewer_comment == "Room is needed"
    assert done.reviewed_by_id == COORD_A and done.resolved_at is not None
    assert db.place(E_CS101) == (1, 1, PRAMAN)


def test_declining_does_not_validate_the_change(db):
    req = make_request("slot", 4)
    mods.modify_schedule(E_MATH120, "slot", 4)  # the proposal now invalid
    done = mods.review_modification(req.id, COORD_A, False)
    assert status_of(done) == "declined"


def test_comment_is_optional(db):
    done = mods.review_modification(make_request().id, COORD_A, False)
    assert done.reviewer_comment is None


# review_modification: who can review, and when
def test_an_instructor_cannot_review(db):
    req = make_request()
    with pytest.raises(PermissionError, match="Only a coordinator"):
        mods.review_modification(req.id, MWEBB, True)
    assert db.request_rows()[0].status == "pending"
    assert db.place(E_CS101) == (1, 1, PRAMAN)


def test_the_requester_cannot_approve_their_own_request(db):
    req = make_request()
    with pytest.raises(PermissionError):
        mods.review_modification(req.id, PRAMAN, True)


def test_a_different_coordinator_cannot_review(db):
    req = make_request()  # assigned to coordinator A
    with pytest.raises(PermissionError, match="different coordinator"):
        mods.review_modification(req.id, COORD_B, True)
    assert db.request_rows()[0].status == "pending"


def test_unknown_request_raises(db):
    with pytest.raises(
        ValueError, match="No modification request found with ID 999"
    ):
        mods.review_modification(999, COORD_A, True)


def test_unknown_reviewer_raises(db):
    with pytest.raises(ValueError, match="No reviewer found with ID 999"):
        mods.review_modification(make_request().id, 999, True)


@pytest.mark.parametrize("second_accept", [True, False])
def test_a_resolved_request_cannot_be_reviewed_again(db, second_accept):
    req = make_request("slot", 4)
    mods.review_modification(req.id, COORD_A, True, "first")
    with pytest.raises(ValueError, match="already been accepted"):
        mods.review_modification(req.id, COORD_A, second_accept, "second")
    stored = db.request_rows()[0]
    assert stored.status == "accepted" and stored.reviewer_comment == "first"
    assert db.place(E_CS101) == (1, 4, PRAMAN)


def test_a_declined_request_cannot_be_accepted_later(db):
    req = make_request("slot", 4)
    mods.review_modification(req.id, COORD_A, False)
    with pytest.raises(ValueError, match="already been declined"):
        mods.review_modification(req.id, COORD_A, True)
    assert db.place(E_CS101) == (1, 1, PRAMAN)
