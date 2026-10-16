import enum
import json
from types import SimpleNamespace as NS

import pytest

from app.scheduler import (
    HARD_PENALTY,
    InfeasibleError,
    ScheduleResult,
    _Scheduler,
    generate_schedule,
)


# Row builders
def room(id, capacity=30, zone="A"):
    return NS(id=id, name=f"Room{id}", zone=zone, capacity=capacity)


def slot(id, hour):
    return NS(id=id, hour=hour, label=f"{hour}h")


def instructor(id, lo=0, hi=3):
    return NS(
        id=id, full_name=f"Inst{id}", min_course_load=lo, max_course_load=hi
    )


def course(id, enrollment=25):
    return NS(id=id, code=f"C{id}", enrollment=enrollment)


def pref(course_id, instructor_id, kind="preferred"):
    return NS(course_id=course_id, instructor_id=instructor_id, preference=kind)


def rule(a, b, kind):
    return NS(course_a_id=a, course_b_id=b, rule_type=kind)


def build(rooms, slots, instructors, courses, prefs, rules=()):
    """A _Scheduler for calling evaluate() directly (the search itself isn't run)."""
    return _Scheduler(
        rooms, slots, instructors, courses, prefs, rules, 10, 10, 10, None, 0
    )


def ev(sched, inst, room, slot):
    """Evaluate one individual given 0-based index lists; returns (total, per_entry, detail)."""
    detail = {"hard": [], "soft": []}
    total, per_entry = sched.evaluate((inst, room, slot), detail)
    return total, per_entry, detail


def one_course(*, capacity=30, enrollment=25, kind="preferred", lo=0, hi=3):
    """One course, one room, one slot, one instructor: the simplest schedulable problem."""
    return build(
        [room(1, capacity)],
        [slot(1, 9)],
        [instructor(1, lo, hi)],
        [course(1, enrollment)],
        [pref(1, 1, kind)],
    )


# Scoring: per-course terms
def test_preferred_instructor_in_well_sized_room():
    total, per_entry, detail = ev(one_course(), [0], [0], [0])
    assert total == pytest.approx(0.5 + 0.3)  # preferred + good room size
    assert per_entry == [pytest.approx(0.8)]
    assert detail == {"hard": [], "soft": []}


def test_qualified_instructor_scores_less_than_preferred():
    total, _, _ = ev(one_course(kind="qualified"), [0], [0], [0])
    assert total == pytest.approx(0.2 + 0.3)


@pytest.mark.parametrize(
    "capacity, size_score, expect_message",
    [
        (30, 0.3, False),  # 1.2x enrollment: fine
        (37, 0.3, False),  # exactly 1.48x: still fine
        (38, -0.2, True),  # just over 1.5x: somewhat large
        (75, -0.2, True),  # exactly 3x: still "somewhat large"
        (76, -0.4, True),  # over 3x: far too large
    ],
)
def test_room_size_bands(capacity, size_score, expect_message):
    sched = one_course(capacity=capacity, enrollment=25)
    total, _, detail = ev(sched, [0], [0], [0])
    assert total == pytest.approx(0.5 + size_score)
    assert bool(detail["soft"]) is expect_message


# Scoring: hard constraints
def test_two_courses_in_same_room_and_slot_is_a_hard_violation():
    sched = build(
        [room(1)],
        [slot(1, 9)],
        [instructor(1), instructor(2)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 2)],
    )
    total, per_entry, detail = ev(sched, [0, 1], [0, 0], [0, 0])
    assert per_entry == [pytest.approx(0.8 - HARD_PENALTY)] * 2
    assert total == pytest.approx(2 * (0.8 - HARD_PENALTY))
    assert len(detail["hard"]) == 1
    assert (
        "C1" in detail["hard"][0]
        and "C2" in detail["hard"][0]
        and "Room1" in detail["hard"][0]
    )


def test_three_courses_in_one_cell_penalise_each_for_both_others():
    sched = build(
        [room(1)],
        [slot(1, 9)],
        [instructor(i) for i in (1, 2, 3)],
        [course(i) for i in (1, 2, 3)],
        [pref(i, i) for i in (1, 2, 3)],
    )
    _, per_entry, _ = ev(sched, [0, 1, 2], [0, 0, 0], [0, 0, 0])
    assert per_entry == [pytest.approx(0.8 - 2 * HARD_PENALTY)] * 3


def test_instructor_teaching_two_courses_in_one_slot_is_a_hard_violation():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9)],
        [instructor(1)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 1)],
    )
    _, per_entry, detail = ev(sched, [0, 0], [0, 1], [0, 0])
    assert per_entry == [pytest.approx(0.8 - HARD_PENALTY)] * 2
    assert len(detail["hard"]) == 1 and "Inst1" in detail["hard"][0]


def test_a_valid_schedule_has_no_hard_violations():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9), slot(2, 12)],
        [instructor(1), instructor(2)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 2)],
    )
    _, _, detail = ev(sched, [0, 1], [0, 1], [0, 1])
    assert detail["hard"] == []


# Scoring: instructor load
def test_overload_penalises_each_of_the_instructors_courses():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9), slot(2, 11)],
        [instructor(1, lo=0, hi=1)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 1)],
    )
    _, per_entry, detail = ev(
        sched, [0, 0], [0, 1], [0, 1]
    )  # 2 courses, max 1, 2h apart
    assert per_entry == [pytest.approx(0.8 - 0.5)] * 2
    assert detail["soft"] == ["Inst1 has 2 courses (max 1)"]


def test_underload_penalises_the_instructors_courses():
    sched = one_course(lo=2)
    total, _, detail = ev(sched, [0], [0], [0])
    assert total == pytest.approx(0.8 - 0.4)
    assert detail["soft"] == ["Inst1 has 1 courses (min 2)"]


def test_load_exactly_at_min_and_max_is_fine():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9), slot(2, 11)],
        [instructor(1, lo=2, hi=2)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 1)],
    )
    _, per_entry, detail = ev(sched, [0, 0], [0, 1], [0, 1])
    assert per_entry == [pytest.approx(0.8)] * 2
    assert detail["soft"] == []


def test_instructor_with_a_minimum_but_no_courses_lowers_total_only():
    sched = build(
        [room(1)],
        [slot(1, 9)],
        [instructor(1), instructor(2, lo=2)],
        [course(1)],
        [pref(1, 1), pref(1, 2)],
    )
    total, per_entry, detail = ev(sched, [0], [0], [0])  # Inst2 gets nothing
    assert per_entry == [pytest.approx(0.8)]  # no entry carries the penalty
    assert total == pytest.approx(0.8 - 0.4 * 2)  # ...so it hits the total
    assert detail["soft"] == ["Inst2 has 0 courses (min 2)"]


def test_instructor_with_no_minimum_and_no_courses_is_not_penalised():
    sched = build(
        [room(1)],
        [slot(1, 9)],
        [instructor(1), instructor(2, lo=0)],
        [course(1)],
        [pref(1, 1), pref(1, 2)],
    )
    total, _, detail = ev(sched, [0], [0], [0])
    assert total == pytest.approx(0.8)
    assert detail["soft"] == []


# Scoring: back-to-back courses for one instructor
def back_to_back(zone_b):
    sched = build(
        [room(1, zone="A"), room(2, zone=zone_b)],
        [slot(1, 9), slot(2, 10)],
        [instructor(1)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 1)],
    )
    return ev(sched, [0, 0], [0, 1], [0, 1])


def test_back_to_back_in_same_zone_is_rewarded():
    _, per_entry, detail = back_to_back("A")
    assert per_entry == [pytest.approx(0.8 + 0.5)] * 2
    assert detail["soft"] == []


def test_back_to_back_in_different_zones_is_mostly_cancelled_out():
    _, per_entry, detail = back_to_back("B")
    assert per_entry == [pytest.approx(0.8 + 0.5 - 0.4)] * 2
    assert len(detail["soft"]) == 1 and "different zones" in detail["soft"][0]


def test_two_hour_gap_is_not_back_to_back():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9), slot(2, 11)],
        [instructor(1)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 1)],
    )
    _, per_entry, _ = ev(sched, [0, 0], [0, 1], [0, 1])
    assert per_entry == [pytest.approx(0.8)] * 2


# Scoring: course-pair rules
def pair_case(kind, hour_a, hour_b, same_zone=True):
    hours = sorted({hour_a, hour_b})
    slots = [slot(i + 1, h) for i, h in enumerate(hours)]
    idx = {h: i for i, h in enumerate(hours)}
    rooms = [room(1, zone="A"), room(2, zone="A" if same_zone else "B")]
    sched = build(
        rooms,
        slots,
        [instructor(1), instructor(2)],
        [course(1), course(2)],
        [pref(1, 1), pref(2, 2)],
        [rule(1, 2, kind)],
    )
    return ev(sched, [0, 1], [0, 1], [idx[hour_a], idx[hour_b]])


@pytest.mark.parametrize(
    "kind, hour_a, hour_b, same_zone, delta, expect_message",
    [
        ("spread", 9, 15, True, +0.5, False),
        ("spread", 9, 14, True, +0.5, False),
        (
            "spread",
            9,
            13,
            True,
            0.0,
            False,
        ),
        ("spread", 9, 10, True, 0.0, False),
        ("spread", 9, 9, True, -0.5, True),
        ("related", 9, 10, True, +0.5, False),
        (
            "related",
            9,
            10,
            False,
            +0.5 - 0.4,
            True,
        ),
        ("related", 9, 11, True, +0.25, False),
        ("related", 9, 12, True, 0.0, False),
        ("related", 9, 9, True, -0.25, True),
    ],
)
def test_pair_rules(kind, hour_a, hour_b, same_zone, delta, expect_message):
    _, per_entry, detail = pair_case(kind, hour_a, hour_b, same_zone)
    assert per_entry == [pytest.approx(0.8 + delta)] * 2
    assert bool(detail["soft"]) is expect_message
    assert detail["hard"] == []


def test_pair_rule_naming_a_course_outside_the_input_is_ignored():
    sched = build(
        [room(1)],
        [slot(1, 9)],
        [instructor(1)],
        [course(1)],
        [pref(1, 1)],
        [rule(1, 99, "spread"), rule(98, 99, "related")],
    )
    assert sched.pairs == []
    total, _, _ = ev(sched, [0], [0], [0])
    assert total == pytest.approx(0.8)


# Input handling
class PrefEnum(str, enum.Enum):
    preferred = "preferred"
    qualified = "qualified"


class RuleEnum(enum.Enum):
    spread = "spread"
    related = "related"


def test_enum_members_are_accepted_for_preference_and_rule_type():
    sched = build(
        [room(1), room(2)],
        [slot(1, 9), slot(2, 15)],
        [instructor(1), instructor(2)],
        [course(1), course(2)],
        [pref(1, 1, PrefEnum.preferred), pref(2, 2, PrefEnum.qualified)],
        [rule(1, 2, RuleEnum.spread)],
    )
    _, per_entry, _ = ev(sched, [0, 1], [0, 1], [0, 1])
    assert per_entry == [
        pytest.approx(0.5 + 0.3 + 0.5),
        pytest.approx(0.2 + 0.3 + 0.5),
    ]


def test_preference_rows_for_unknown_instructors_are_ignored():
    result = generate_schedule(
        [room(1)],
        [slot(1, 9)],
        [instructor(1)],
        [course(1)],
        [pref(1, 1), pref(1, 99)],
        population_size=20,
        seed=1,
    )
    assert result.entries[0]["instructor_id"] == 1


# Infeasible input fails fast with a useful message
def test_course_with_no_linked_instructor_is_rejected():
    with pytest.raises(InfeasibleError, match="C1.*no instructor"):
        generate_schedule(
            [room(1)], [slot(1, 9)], [instructor(1)], [course(1)], []
        )


def test_course_linked_only_to_an_unknown_instructor_is_rejected():
    with pytest.raises(InfeasibleError, match="C1.*no instructor"):
        generate_schedule(
            [room(1)], [slot(1, 9)], [instructor(1)], [course(1)], [pref(1, 99)]
        )


def test_course_too_big_for_every_room_is_rejected():
    with pytest.raises(InfeasibleError, match="C1.*no room holds 50"):
        generate_schedule(
            [room(1, capacity=40)],
            [slot(1, 9)],
            [instructor(1)],
            [course(1, enrollment=50)],
            [pref(1, 1)],
        )


def test_every_problem_is_reported_at_once():
    with pytest.raises(InfeasibleError) as err:
        generate_schedule(
            [room(1, capacity=10)],
            [slot(1, 9)],
            [instructor(1)],
            [course(1), course(2)],
            [pref(2, 1)],
        )
    message = str(err.value)
    assert (
        "C1: no instructor" in message
        and "C1: no room" in message
        and "C2: no room" in message
    )


def test_infeasible_error_is_a_value_error():
    assert issubclass(InfeasibleError, ValueError)


@pytest.mark.parametrize("empty", ["rooms", "slots", "instructors", "courses"])
def test_empty_inputs_are_rejected(empty):
    args = {
        "rooms": [room(1)],
        "slots": [slot(1, 9)],
        "instructors": [instructor(1)],
        "courses": [course(1)],
    }
    args[empty] = []
    with pytest.raises(InfeasibleError, match="non-empty"):
        generate_schedule(
            args["rooms"],
            args["slots"],
            args["instructors"],
            args["courses"],
            [pref(1, 1)],
        )


# End to end on a small semester
@pytest.fixture(scope="module")
def semester():
    rooms = [
        room(1, 120, "Main"),
        room(2, 60, "Main"),
        room(3, 80, "Main"),
        room(4, 40, "Main"),
        room(5, 30, "North"),
        room(6, 24, "North"),
    ]
    slots = [slot(i + 1, 9 + i) for i in range(7)]
    instructors = [instructor(i, lo=1, hi=3) for i in range(1, 7)]
    courses = [
        course(1, 40),
        course(2, 35),
        course(3, 50),
        course(4, 30),
        course(5, 45),
        course(6, 25),
        course(7, 90),
        course(8, 55),
    ]
    teaching = {
        1: ([1, 2, 3], [4]),
        2: ([4, 6], [3, 5]),
        3: ([5, 3], [1, 2]),
        4: ([7, 8], [5]),
        5: ([7], [8, 4]),
        6: ([6, 4], [2]),
    }
    prefs = [
        pref(c, i, kind)
        for i, (pr, ql) in teaching.items()
        for cs, kind in ((pr, "preferred"), (ql, "qualified"))
        for c in cs
    ]
    rules = [
        rule(1, 2, "spread"),
        rule(1, 7, "related"),
        rule(2, 7, "related"),
        rule(3, 8, "related"),
    ]
    return NS(
        rooms=rooms,
        slots=slots,
        instructors=instructors,
        courses=courses,
        prefs=prefs,
        rules=rules,
    )


def run(semester, **options):
    return generate_schedule(
        semester.rooms,
        semester.slots,
        semester.instructors,
        semester.courses,
        semester.prefs,
        semester.rules,
        **options,
    )


@pytest.fixture(scope="module")
def results(semester):
    return [run(semester, seed=seed) for seed in range(3)]


def assert_valid(result, semester):
    """Every hard constraint, checked independently of the scheduler's own scoring."""
    rooms = {r.id: r for r in semester.rooms}
    courses = {c.id: c for c in semester.courses}
    linked = {(p.course_id, p.instructor_id) for p in semester.prefs}

    assert sorted(e["course_id"] for e in result.entries) == sorted(courses)
    for e in result.entries:
        assert (e["course_id"], e["instructor_id"]) in linked
        assert (
            rooms[e["room_id"]].capacity >= courses[e["course_id"]].enrollment
        )
    cells = [(e["time_slot_id"], e["room_id"]) for e in result.entries]
    assert len(cells) == len(set(cells)), "a room is double-booked"
    teaching = [(e["instructor_id"], e["time_slot_id"]) for e in result.entries]
    assert len(teaching) == len(set(teaching)), "an instructor is double-booked"


def test_result_satisfies_every_hard_constraint(results, semester):
    for result in results:
        assert_valid(result, semester)
        assert result.report["hard_violations"] == []


def test_result_is_a_schedule_result_with_db_ready_entries(results):
    result = results[0]
    assert isinstance(result, ScheduleResult)
    assert all(
        set(e)
        == {"course_id", "instructor_id", "room_id", "time_slot_id", "fitness"}
        for e in result.entries
    )
    assert all(isinstance(e["fitness"], float) for e in result.entries)


def test_quality_is_close_to_the_best_known_score(results):
    for result in results:
        assert result.fitness >= 11.0


def test_total_fitness_is_the_sum_of_entry_fitness_plus_zero_load_penalties(
    results, semester
):
    for result in results:
        used = {e["instructor_id"] for e in result.entries}
        idle_penalty = sum(
            0.4 * i.min_course_load
            for i in semester.instructors
            if i.id not in used
        )
        assert result.fitness == pytest.approx(
            sum(e["fitness"] for e in result.entries) - idle_penalty, abs=0.02
        )


def test_soft_violation_messages_match_what_the_schedule_actually_has(results):
    for result in results:
        soft = result.report["soft_violations"]
        assert all(isinstance(m, str) for m in soft)
        used = {e["instructor_id"] for e in result.entries}
        for i in range(1, 7):
            assert (f"Inst{i} has 0 courses (min 1)" in soft) == (i not in used)


# Report, history, and stopping rules
def test_report_has_the_expected_shape_and_is_json_serialisable(results):
    result = results[0]
    assert set(result.report) == {
        "soft_violations",
        "hard_violations",
        "history",
    }
    json.dumps(result.report)
    json.dumps(result.entries)


def test_history_has_one_row_per_generation(results):
    for result in results:
        history = result.report["history"]
        assert len(history) == result.generations_run
        assert [h["generation"] for h in history] == list(
            range(1, result.generations_run + 1)
        )
        assert all(
            set(h) == {"generation", "best", "average", "worst"}
            for h in history
        )
        assert all(h["worst"] <= h["average"] <= h["best"] for h in history)


def test_best_score_never_gets_worse_between_generations(results):
    for result in results:
        best = [h["best"] for h in result.report["history"]]
        assert best == sorted(best)


def test_generation_found_matches_the_history(results):
    for result in results:
        history = result.report["history"]
        assert 1 <= result.generation_found <= result.generations_run
        found = history[result.generation_found - 1]["best"]
        assert found == pytest.approx(
            max(h["best"] for h in history), abs=0.001
        )
        assert all(
            h["best"] <= found + 1e-9
            for h in history[result.generation_found :]
        )


def test_max_generations_is_a_hard_cap(semester):
    result = run(
        semester, seed=1, population_size=30, max_generations=5, patience=1000
    )
    assert result.generations_run == 5
    assert len(result.report["history"]) == 5


def test_patience_stops_the_run_after_that_many_stale_generations(semester):
    result = run(
        semester, seed=1, population_size=30, patience=3, max_generations=500
    )
    assert result.generations_run == result.generation_found + 3


def test_progress_callback_receives_every_generation(semester):
    seen = []
    result = run(
        semester,
        seed=2,
        population_size=30,
        max_generations=8,
        patience=1000,
        progress=seen.append,
    )
    assert [s["generation"] for s in seen] == list(range(1, 9))
    assert seen == result.report["history"]


# Determinism and edge cases
def test_same_seed_gives_the_same_schedule(semester):
    a = run(semester, seed=7, population_size=50)
    b = run(semester, seed=7, population_size=50)
    assert a.entries == b.entries
    assert a.fitness == b.fitness
    assert a.report == b.report


def test_a_single_course_can_be_scheduled():
    result = generate_schedule(
        [room(1)],
        [slot(1, 9), slot(2, 10)],
        [instructor(1)],
        [course(1)],
        [pref(1, 1)],
        population_size=20,
        seed=1,
    )
    assert len(result.entries) == 1
    assert result.entries[0]["fitness"] == pytest.approx(0.8)


def test_courses_outside_the_input_are_never_scheduled(semester):
    subset = NS(
        **{**semester.__dict__, "courses": semester.courses[:3]}
    )  # prefs/rules mention the rest
    result = run(subset, seed=1, population_size=50)
    assert sorted(e["course_id"] for e in result.entries) == [1, 2, 3]


def test_default_mutation_rate_scales_with_the_number_of_courses(semester):
    sched = build(
        semester.rooms,
        semester.slots,
        semester.instructors,
        semester.courses,
        semester.prefs,
    )
    assert sched.mutation_rate == pytest.approx(2 / 8)
    one = build(
        [room(1)], [slot(1, 9)], [instructor(1)], [course(1)], [pref(1, 1)]
    )
    assert one.mutation_rate == 1.0  # capped at 1


def test_genetic_operators_only_ever_produce_valid_individuals(semester):
    sched = build(
        semester.rooms,
        semester.slots,
        semester.instructors,
        semester.courses,
        semester.prefs,
    )
    population = [sched._random_individual() for _ in range(40)]
    fitnesses = [sched.evaluate(ind)[0] for ind in population]
    children = sched._crossover(population, fitnesses, 40)
    assert len(children) == 40
    for child in children:
        sched._mutate(child, 1.0)  # mutate every gene
    for inst, rm, sl in population + children:
        assert len(inst) == len(rm) == len(sl) == sched.n
        for c in range(sched.n):
            assert inst[c] in sched.cand_inst[c]
            assert rm[c] in sched.cand_room[c]
            assert 0 <= sl[c] < sched.n_slots
