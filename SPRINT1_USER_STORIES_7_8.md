# Sprint 1: User Stories 7 and 8

## Current status

User Story 7 is integrated into the current JWT-authenticated frontend. Story 8 now has independent Google Calendar OAuth, encrypted credential storage, connection status, mocked event insertion, and persistent duplicate prevention.

Real schedule synchronization can use the explicitly opt-in temporary Spring 2027 demo dates. Official schedule synchronization remains blocked until real schedule dates or recurrence data are supplied. No schedule-generation tables were changed, and no database migration was executed.

The Git stash was inspected but not applied or dropped. Its old `frontend/pages/` files were not restored because Development uses `frontend/views/` and `st.navigation`.

## Acceptance criteria

### AC 7.1: View all open modification requests

Status: **Implemented and tested.**

An authenticated coordinator opens Requests and selects `View Requests`. The page calls `GET /requests/open` with the shared JWT and displays every pending request, including requests assigned to another coordinator. An empty result shows `No open modification requests.`. The existing `/modifications` review workflow remains unchanged.

### AC 8.1: Push a generated schedule to a linked calendar

Status: **Demo synchronization implemented; official dates remain pending.**

Instructors can connect Google Calendar, view connection status, and use `Push to Calendar`. When `CALENDAR_DEMO_MODE=true`, each owned schedule entry becomes a Monday/Wednesday recurring event from January 11 through May 7, 2027, with America/Chicago timezone and a 60-minute duration. When disabled, the endpoint preserves the missing-date validation error. Synthetic event insertion is tested with mocked Google API calls; no live Google authorization or event insertion was claimed.

### AC 8.2: No linked calendar

Status: **Implemented and tested.**

Missing, plaintext, invalid, or undecryptable credentials are treated as disconnected. Push returns `404 No calendar found` before any Google service is constructed, and the frontend displays the backend message.

## Production files

### Existing and reused

- `backend/app/api/deps.py`: shared JWT authentication and role checks.
- `frontend/auth.py`: Streamlit session and JWT storage.
- `frontend/api_client.py`: authenticated backend requests.
- `backend/app/api/scheduling.py`: existing modification workflow.
- `backend/app/models/calendar.py`: existing `CalendarLink` model.

### Story 7 integration

- `frontend/views/modification_requests.py`: coordinator all-pending `View Requests` action.
- `backend/app/api/requests.py`: protected `GET /requests/open`.
- `backend/app/core/auth.py`: adapts Story 7 dependencies to shared JWT auth.
- `backend/app/main.py`: registers the request and calendar routers.

### Story 8 integration

- `backend/app/api/calendar_oauth.py`: instructor-only OAuth start, callback, and connection-status endpoints.
- `backend/app/services/calendar_security.py`: Fernet encryption/decryption for refresh tokens.
- `backend/app/services/calendar.py`: event validation, credential refresh, Google insertion, and duplicate-safe insertion orchestration.
- `backend/app/services/calendar_demo.py`: opt-in demo dates and recurring event construction.
- `backend/app/models/calendar.py`: `CalendarOAuthState` and `CalendarEventSync` models.
- `frontend/views/schedules.py`: instructor connection status, Connect Google Calendar, and authenticated Push to Calendar controls.
- `backend/alembic/versions/9f2e_calendar_oauth_sync.py`: proposed migration, not executed.

## OAuth routes

- `GET /calendar/oauth/connect`: authenticated instructor only; creates a one-time hashed state and returns the Google authorization URL.
- `GET /calendar/oauth/callback`: public Google redirect endpoint; validates state, expiry, and one-time use before exchanging the code.
- `GET /calendar/status`: authenticated instructor status; only decryptable credentials are reported as connected.
- `POST /calendar/push`: existing authenticated instructor endpoint; missing schedule dates remain a 422 validation response.

## Security and synchronization design

- Scope is limited to `https://www.googleapis.com/auth/calendar.events`.
- OAuth state is generated with `secrets.token_urlsafe`, stored only as a SHA-256 hash, bound to the instructor, expires after ten minutes, and is marked used after successful linking.
- Refresh tokens are encrypted with Fernet using `CALENDAR_TOKEN_ENCRYPTION_KEY`; plaintext tokens are never returned to Streamlit or written to source control.
- Expired access tokens are refreshed through Google credentials. Revoked authorization is surfaced as a safe error.
- Each event requires a stable `_coursecorrect_event_key`. Successful Google IDs are stored in `calendar_event_syncs`; repeated pushes skip existing keys, while failed inserts remain retryable.
- Each successful insert is committed independently so partial failures do not lose earlier successful synchronization records.

## Dependencies and configuration

Added to `backend/requirements.txt`:

- `cryptography`
- `google-api-python-client`
- `google-auth`
- `google-auth-oauthlib`

Local setup generates a development Fernet key. Production must provide a stable secret through environment configuration. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and `CALENDAR_TOKEN_ENCRYPTION_KEY` without committing them.

Demo mode is controlled by `CALENDAR_DEMO_MODE` and is disabled by default. Enable it only for the Sprint 1 demonstration:

```text
CALENDAR_DEMO_MODE=true
```

## Proposed migration

`backend/alembic/versions/9f2e_calendar_oauth_sync.py` adds:

- `calendar_oauth_states`: hashed one-time state, instructor, expiry, and use time.
- `calendar_event_syncs`: calendar link, stable event key, Google event ID, and timestamps.

The migration has **not** been executed. Run it only after review and approval:

```text
python3 scripts/dev.py migrate
```

## Automated tests

`backend/tests/test_calendar_integration.py` covers OAuth state rejection and replay, instructor authorization, encrypted linking, encryption round trips, missing-calendar status, token revocation, duplicate prevention, and partial failures using mocked Google behavior.

`backend/tests/test_user_stories_7_8.py` covers Story 7 all-pending visibility, missing-date validation, missing-calendar behavior, and synthetic event construction.

No live Google Calendar test was run. The current Google client warning notes that the installed Python 3.10 version is approaching the dependency support floor.

## Remaining limitations and manual verification

The current schema has only `TimeSlot.hour` and `TimeSlot.label`; it has no weekday, semester start/end date, timezone, or recurrence rule. Do not use `Schedule.created_at` as a class date. The schedule owner must supply those semantics before `/calendar/push` can create official events. Demo mode uses only the temporary assumptions documented in `calendar_demo.py`.

Google Cloud Console setup required:

1. Create or select a Google Cloud project.
2. Enable the Google Calendar API.
3. Configure an OAuth consent screen.
4. Create a Web application OAuth client.
5. Add the exact local redirect URI from `GOOGLE_REDIRECT_URI`.
6. Provide the client ID and secret only through environment variables.

Manual checks:

1. Log in as a coordinator and use Requests > `View Requests`.
2. Log in as an instructor and open Schedules.
3. Confirm disconnected status and use `Connect Google Calendar`.
4. With no link, confirm Push displays `No calendar found`.
5. With demo mode enabled and a linked account, confirm Push creates recurring events only after Google confirms insertion.
6. With demo mode disabled, confirm Push displays the missing-date error and does not report success.

Story 7 is ready for review. Story 8 infrastructure is reviewable, but the branch is not ready to claim complete end-to-end calendar synchronization until OAuth configuration and schedule date/recurrence data are available.
