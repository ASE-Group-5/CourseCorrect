from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import accumulate
from typing import Callable

HARD_PENALTY = 5.0
SPREAD_GAP_HOURS = 4

_PREFERENCE_BONUS = {"preferred": 0.5, "qualified": 0.2}


class InfeasibleError(ValueError):
    """Raised before any search starts when the input can't possibly be scheduled."""


@dataclass
class ScheduleResult:
    entries: list[dict]
    fitness: float
    generation_found: int
    generations_run: int
    report: dict


def _value(x):
    """Enum member or plain string -> string."""
    return getattr(x, "value", x)


def _size_score(capacity: int, enrollment: int) -> float:
    if capacity > enrollment * 3.0:
        return -0.4
    if capacity > enrollment * 1.5:
        return -0.2
    return 0.3


class _Scheduler:
    def __init__(
        self,
        rooms,
        time_slots,
        instructors,
        courses,
        preferences,
        pair_rules,
        population_size,
        max_generations,
        patience,
        mutation_rate,
        seed,
    ):
        self.rooms = list(rooms)
        self.slots = list(time_slots)
        self.instructors = list(instructors)
        self.courses = list(courses)
        if not (
            self.rooms and self.slots and self.instructors and self.courses
        ):
            raise InfeasibleError(
                "rooms, time_slots, instructors and courses must all be non-empty"
            )

        self.population_size = population_size
        self.max_generations = max_generations
        self.patience = patience
        self.rng = random.Random(seed)
        self.n = len(self.courses)
        self.mutation_rate = (
            mutation_rate
            if mutation_rate is not None
            else min(1.0, 2.0 / self.n)
        )

        self.hour = [s.hour for s in self.slots]
        zones = {}
        self.zone = [zones.setdefault(r.zone, len(zones)) for r in self.rooms]
        self.n_slots = len(self.slots)

        course_index = {c.id: k for k, c in enumerate(self.courses)}
        instructor_index = {i.id: k for k, i in enumerate(self.instructors)}

        self.pref: list[dict[int, float]] = [{} for _ in self.courses]
        for p in preferences:
            c, i = (
                course_index.get(p.course_id),
                instructor_index.get(p.instructor_id),
            )
            if c is not None and i is not None:
                self.pref[c][i] = _PREFERENCE_BONUS[_value(p.preference)]

        self.cand_room = [
            [
                r
                for r, room in enumerate(self.rooms)
                if room.capacity >= c.enrollment
            ]
            for c in self.courses
        ]
        self.size = [
            [_size_score(room.capacity, c.enrollment) for room in self.rooms]
            for c in self.courses
        ]

        problems = []
        for c, course in enumerate(self.courses):
            if not self.pref[c]:
                problems.append(
                    f"{course.code}: no instructor is linked to this course"
                )
            if not self.cand_room[c]:
                problems.append(
                    f"{course.code}: no room holds {course.enrollment} students"
                )
        if problems:
            raise InfeasibleError(
                "Cannot schedule:\n  " + "\n  ".join(problems)
            )
        self.cand_inst = [list(p) for p in self.pref]

        self.pairs = [
            (
                course_index[r.course_a_id],
                course_index[r.course_b_id],
                _value(r.rule_type),
            )
            for r in pair_rules
            if r.course_a_id in course_index and r.course_b_id in course_index
        ]
        self.must_teach = [
            k for k, i in enumerate(self.instructors) if i.min_course_load > 0
        ]

    # ------------------------------------------------------------------ run
    def run(self, progress: Callable[[dict], None] | None) -> ScheduleResult:
        n_pop = self.population_size
        population = [self._random_individual() for _ in range(n_pop)]
        fitnesses = [self.evaluate(ind)[0] for ind in population]

        # Seed with the best of the initial population
        top_idx = max(range(n_pop), key=fitnesses.__getitem__)
        best, best_fitness, generation_found = (
            population[top_idx],
            fitnesses[top_idx],
            1,
        )
        history = []
        generation = 0

        while True:
            generation += 1
            top_idx = max(range(len(fitnesses)), key=fitnesses.__getitem__)
            if fitnesses[top_idx] > best_fitness + 1e-9:
                best_fitness, best, generation_found = (
                    fitnesses[top_idx],
                    population[top_idx],
                    generation,
                )

            stats = {
                "generation": generation,
                "best": round(fitnesses[top_idx], 3),
                "average": round(sum(fitnesses) / len(fitnesses), 3),
                "worst": round(min(fitnesses), 3),
            }
            history.append(stats)
            if progress:
                progress(stats)

            if (
                generation - generation_found >= self.patience
                or generation >= self.max_generations
            ):
                break

            offspring = self._crossover(population, fitnesses, n_pop)
            for child in offspring:
                self._mutate(child, self.mutation_rate)
            off_fitnesses = [self.evaluate(ind)[0] for ind in offspring]

            ranked = sorted(
                zip(fitnesses + off_fitnesses, population + offspring),
                key=lambda pair: pair[0],
                reverse=True,
            )[:n_pop]
            fitnesses = [f for f, _ in ranked]
            population = [p for _, p in ranked]

        detail = {"hard": [], "soft": []}
        total, per_entry = self.evaluate(best, detail)
        inst, room, slot = best
        entries = [
            {
                "course_id": self.courses[c].id,
                "instructor_id": self.instructors[inst[c]].id,
                "room_id": self.rooms[room[c]].id,
                "time_slot_id": self.slots[slot[c]].id,
                "fitness": round(per_entry[c], 2),
            }
            for c in range(self.n)
        ]
        report = {
            "soft_violations": detail["soft"],
            "hard_violations": detail["hard"],
            "history": history,
        }
        return ScheduleResult(
            entries, round(total, 2), generation_found, generation, report
        )

    # ------------------------------------------------------ genetic operators
    def _random_individual(self):
        r, n = self.rng, self.n
        return (
            [r.choice(self.cand_inst[c]) for c in range(n)],
            [r.choice(self.cand_room[c]) for c in range(n)],
            [r.randrange(self.n_slots) for _ in range(n)],
        )

    def _mutate(self, ind, rate):
        r = self.rng
        inst, room, slot = ind
        for c in range(self.n):
            if r.random() < rate:
                gene = r.randrange(3)
                if gene == 0:
                    inst[c] = r.choice(self.cand_inst[c])
                elif gene == 1:
                    room[c] = r.choice(self.cand_room[c])
                else:
                    slot[c] = r.randrange(self.n_slots)

    def _crossover(self, population, fitnesses, count):
        """Single-point crossover; parents drawn with softmax-weighted fitness."""
        r = self.rng
        top = max(fitnesses)
        cum_weights = list(accumulate(math.exp(f - top) for f in fitnesses))
        offspring = []
        while len(offspring) < count:
            p1, p2 = r.choices(population, cum_weights=cum_weights, k=2)
            cut = r.randint(1, self.n - 1) if self.n > 1 else 0
            offspring.append(tuple(a[:cut] + b[cut:] for a, b in zip(p1, p2)))
            offspring.append(tuple(b[:cut] + a[cut:] for a, b in zip(p1, p2)))
        return offspring[:count]

    # ---------------------------------------------------------------- fitness
    def evaluate(self, ind, detail=None):
        """Return (total fitness, per-course fitness list)."""
        inst, room, slot = ind
        n, hour, zone = self.n, self.hour, self.zone
        courses, rooms, slots, instructors = (
            self.courses,
            self.rooms,
            self.slots,
            self.instructors,
        )
        score = [
            self.pref[c][inst[c]] + self.size[c][room[c]] for c in range(n)
        ]

        def note(kind, message):
            if detail is not None:
                detail[kind].append(message())

        cells = {}
        for c in range(n):
            cells.setdefault((slot[c], room[c]), []).append(c)
        for (s, r), group in cells.items():
            if len(group) > 1:
                for c in group:
                    score[c] -= HARD_PENALTY * (len(group) - 1)
                note(
                    "hard",
                    lambda: (
                        f"{', '.join(courses[c].code for c in group)} all in "
                        f"{rooms[r].name} at {slots[s].label}"
                    ),
                )

        loads = {}
        for c in range(n):
            loads.setdefault(inst[c], []).append(c)

        for i, group in loads.items():
            who = instructors[i]

            same_slot = {}
            for c in group:
                same_slot.setdefault(slot[c], []).append(c)
            for s, clash in same_slot.items():
                if len(clash) > 1:
                    for c in clash:
                        score[c] -= HARD_PENALTY
                    note(
                        "hard",
                        lambda: (
                            f"{who.full_name} teaches {', '.join(courses[c].code for c in clash)} "
                            f"at {slots[s].label}"
                        ),
                    )

            total = len(group)
            if total > who.max_course_load:
                for c in group:
                    score[c] -= 0.5
                note(
                    "soft",
                    lambda: (
                        f"{who.full_name} has {total} courses (max {who.max_course_load})"
                    ),
                )
            elif total < who.min_course_load:
                for c in group:
                    score[c] -= 0.4
                note(
                    "soft",
                    lambda: (
                        f"{who.full_name} has {total} courses (min {who.min_course_load})"
                    ),
                )

            for c in group:
                for d in group:
                    if c != d and abs(hour[slot[c]] - hour[slot[d]]) == 1:
                        score[c] += 0.5
                        if zone[room[c]] != zone[room[d]]:
                            score[c] -= 0.4
                            if c < d:
                                note(
                                    "soft",
                                    lambda: (
                                        f"{who.full_name} has back-to-back {courses[c].code} "
                                        f"({rooms[room[c]].name}) and {courses[d].code} "
                                        f"({rooms[room[d]].name}) in different zones"
                                    ),
                                )

        if detail is not None:
            for c in range(n):
                if self.size[c][room[c]] < 0:
                    note(
                        "soft",
                        lambda: (
                            f"{rooms[room[c]].name} (capacity {rooms[room[c]].capacity}) is "
                            f"oversized for {courses[c].code} (enrollment {courses[c].enrollment})"
                        ),
                    )

        for a, b, kind in self.pairs:
            gap = abs(hour[slot[a]] - hour[slot[b]])
            delta = 0.0
            if kind == "spread":
                if gap > SPREAD_GAP_HOURS:
                    delta = 0.5
                elif gap == 0:
                    delta = -0.5
                    note(
                        "soft",
                        lambda: (
                            f"{courses[a].code} and {courses[b].code} should be spread out "
                            f"but are both at {slots[slot[a]].label}"
                        ),
                    )
            else:
                if gap == 1:
                    delta = 0.5
                    if zone[room[a]] != zone[room[b]]:
                        delta -= 0.4
                        note(
                            "soft",
                            lambda: (
                                f"Related {courses[a].code} and {courses[b].code} are back-to-back "
                                f"in different zones"
                            ),
                        )
                elif gap == 2:
                    delta = 0.25
                elif gap == 0:
                    delta = -0.25
                    note(
                        "soft",
                        lambda: (
                            f"Related {courses[a].code} and {courses[b].code} are both at "
                            f"{slots[slot[a]].label}"
                        ),
                    )
            if delta:
                score[a] += delta
                score[b] += delta

        total = sum(score)

        for i in self.must_teach:
            if i not in loads:
                total -= 0.4 * instructors[i].min_course_load
                note(
                    "soft",
                    lambda: (
                        f"{instructors[i].full_name} has 0 courses "
                        f"(min {instructors[i].min_course_load})"
                    ),
                )
        return total, score


def generate_schedule(
    rooms,
    time_slots,
    instructors,
    courses,
    preferences,
    pair_rules=(),
    *,
    population_size: int = 300,
    max_generations: int = 500,
    patience: int = 40,
    mutation_rate: float | None = None,
    seed: int | None = None,
    progress: Callable[[dict], None] | None = None,
) -> ScheduleResult:
    """Evolve a schedule for the given courses.
    Stops when the best score hasn't improved for `patience` generations
    """
    return _Scheduler(
        rooms,
        time_slots,
        instructors,
        courses,
        preferences,
        pair_rules,
        population_size,
        max_generations,
        patience,
        mutation_rate,
        seed,
    ).run(progress)
