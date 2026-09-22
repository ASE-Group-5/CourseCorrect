# CourseCorrect

A web application used in a university system that automates the creation of coherent adjustable schedules of classes and events which takes into account user input and constraints.

## Overview

Scheduling courses each semester is a complex, constraint-heavy process. This project automates semester schedule generation while streamlining communication between coordinators and instructors.

## Features

- **Automated Schedule Generation** — Generates a semester schedule that can accomodate:
  - **Hard constraints**: room availability, no overlaps between certain courses, class size limits, ....etc
  - **Soft constraints**: based on communication between instructors and coordinators.
- **Coordinator ↔ Instructor Communication**
  - Instructors can communicate preferences and suggest modifications.
  - Only course coordinators can generate or modify the schedule.
- **Calendar Integration**: sync the final schedule to a personal calendar.

## Users

- **Students**: view schedules.
- **Instructors**: submit preferences, view schedules, suggest changes.
- **Administrators / Course Coordinators**: manage courses and instructors, and generate and finalize schedules.

## Tech Stack

- **Language:** Python
- **Database:** PostgreSQL
- **Testing:** Pytest
- **IDE:** VS Code
- **Style Guide:** [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

## Team

- Ramzey Alissa
- Mahjabin Hossain
- Manan Koradiya
- Halena Aquino-Dunkin
