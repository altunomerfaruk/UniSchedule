# UniSchedule

UniSchedule helps students find conflict-free course schedules for Haliç University Software Engineering (English), **2026–2027 Fall**. The catalogue comes from the supplied [timetable PDF](docs/Report.pdf) and runs on local data.

## Features and technologies

- Select courses, exclude sections, and set scheduling preferences as an anonymous visitor.
- Compare up to five valid alternatives, choose one for **My Schedule**, and save or download it as CSV.
- Use the protected administrator panel to add, edit, archive, and restore catalogue entries.

The frontend uses React, TypeScript, and Vite. The backend uses Python, FastAPI, SQLAlchemy, and SQLite.

## Run locally

Requirements: Python 3.11+ and Node.js 20.19+ or 22.12+.

From the project root in PowerShell, install the dependencies once:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ../frontend
npm ci
cd ..
```

On Windows, run `python main.py` from the project root. In VS Code, open the UniSchedule folder, install the Python Debugger extension, select **UniSchedule: Backend + Frontend**, and press **F5**. The launcher uses the backend virtual environment and opens the browser once the frontend can reach the API. Backend Python changes restart the API process. Vite handles frontend changes.

Press Ctrl+C in the launcher terminal or stop the VS Code debug session to close the servers it started. Run the same command or press F5 again to restart. If both UniSchedule servers are already running, the launcher opens that instance and leaves it under the original session's control. Use `python main.py --no-browser` to start without opening a browser.

For manual startup, run `uvicorn app.main:app --host 127.0.0.1 --port 8000` from `backend` with its virtual environment active, and run `npm run dev` from `frontend` in another terminal.

The schedule is at http://127.0.0.1:5173/ and Swagger is at http://127.0.0.1:8000/docs. Visitors can select courses, set preferences, and generate schedules without signing in.

On a fresh copy, the backend creates `backend/unischedule-fall-2026.db` on startup. The tracked catalogue JSON provides the seed data without needing the PDF or an existing database file. To carry local data to another machine, stop the server and make a SQLite backup. Restore the backup in the same location before starting the app. The database, local credentials, virtual environment, and build output are ignored by Git.

## Administrator access

The management page is at http://127.0.0.1:5173/admin. After sign-in it opens `/admin/dashboard`. There is no public administrator registration page. Course, section, and session changes require an administrator session in the API; the public Courses page has selection and section exclusion controls only.

Create a local development administrator from `backend` after installing requirements:

```powershell
$env:UNISCHEDULE_ENABLE_DEV_BOOTSTRAP = '1'
.\.venv\Scripts\python.exe -m app.provision --dev-admin
```

The command generates a random password and writes the account name and password to the ignored local file `backend/.dev-admin-credentials.json`. It refuses to run when `UNISCHEDULE_ENV=production` and does not overwrite an existing credential file. Keep this file on your own machine. For a non-development installation, provision an administrator with `.\.venv\Scripts\python.exe -m app.provision --create-admin YOUR_NAME`; the command prompts for a password of at least 14 characters. Set `UNISCHEDULE_ENV=production` for Secure cookies and `UNISCHEDULE_ALLOWED_ORIGINS` to the exact site origin. Serve the site over HTTPS in that mode.

Administrator passwords use scrypt with a random salt. Sign-in creates a revocable, expiring HttpOnly session cookie. State-changing administrator requests require a CSRF token, and the API rejects cross-origin writes. Sign-out revokes the session. Administrator credentials are never placed in frontend source or the seed catalogue.

Visitors receive separate anonymous cookies for their preferences and saved schedules. Losing that browser cookie means the old anonymous data is no longer associated with that browser. The five schedules from the earlier single-user version stay in SQLite without being shown to every visitor. A signed-in administrator can explicitly use **Import previous schedules** to attach them to that browser's visitor session. Importing also replaces that browser's course selection with the previous selection.

## Catalogue

`backend/app/data/fall_2026.json` contains **20 courses, 31 sections, and 115 individual session records** transcribed from all three pages of the supplied PDF. Each record keeps its course code, section, weekday, exact start and end time, room type, offering department, source page, and any printed `u` marker. Consecutive 50-minute sessions may share one visual card; the algorithm still checks the original session times. One section always carries all its theory and practical sessions.

The PDF does not provide ECTS, course credits, instructors, mandatory or elective status, or exact room numbers. These fields start empty. The ECTS limit is inactive while a selected course has an unknown ECTS value. Administrators can enter verified values and manage sections and individual sessions in the Admin Panel. The JSON seeds a new database once; restarting the app does not overwrite edits made through the interface. To try a fresh catalogue without changing an existing database, point `DATABASE_URL` to a new SQLite file before starting the backend.

Adding, editing, and deleting courses, sections, and sessions use the administrator-protected FastAPI endpoints listed below. Deletion removes an item from the active catalogue but retains its database record and saved schedule snapshots. The app rechecks affected schedules against active sessions and each visitor's required preferences. A harmless course or section rename stays valid; changed session times or delivery require review; deleted or conflicting sessions make a schedule invalid. The Alternatives page shows each saved schedule's status and reason. Deleting a course also removes it from affected visitors' selections; unselecting a course in the public table does not delete it. Administrators can open **Archived Courses** to restore an accidentally deleted course with its existing sections and sessions. Archived course codes remain reserved for restoration.

| Item | List | Detail | Create | Update | Delete |
| --- | --- | --- | --- | --- | --- |
| Courses | `GET /api/courses` | `GET /api/courses/{id}` | `POST /api/courses` | `PUT /api/courses/{id}` | `DELETE /api/courses/{id}` |
| Sections | `GET /api/courses/{id}/sections` | `GET /api/sections/{id}` | `POST /api/courses/{id}/sections` | `PUT /api/sections/{id}` | `DELETE /api/sections/{id}` |
| Sessions | `GET /api/sections/{id}/sessions` | `GET /api/sessions/{id}` | `POST /api/sections/{id}/sessions` | `PUT /api/sessions/{id}` | `DELETE /api/sessions/{id}` |

`GET /api/courses/archived` lists deleted courses for administrators. `POST /api/courses/{id}/restore` returns one to the active catalogue. `POST /api/admin/login`, `GET /api/admin/me`, and `POST /api/admin/logout` manage administrator sessions; `GET /api/admin/legacy` and `POST /api/admin/claim-legacy` manage the explicit import of previous schedules. Saved schedule snapshots remain unchanged; valid schedules display current course details, while schedules needing review or marked invalid display their saved snapshot.

Course codes are unique without regard to case. Section numbers are unique within a course, and sessions within one section may not overlap. Different courses and sections may share times; schedule generation resolves those conflicts. Monday through Saturday are supported.

Online sessions block time conflicts but do not add a campus day. The Saturday 08:00–08:01 Internship I record remains in the data and does not add a campus day. Preferred free days can include Saturday; the user may make those days a required rule.

## Scheduling

The backtracking service chooses one complete section per selected course, rejects overlaps and required-rule violations, scores valid results for campus days, early classes, long gaps, and preferred free days, then returns up to five actual combinations. If none remain, the API gives a representative course, section, day, and time conflict when it finds one. Generated and saved schedules use the Fall SQLite database.

## Project structure

```text
.
├── .codex/                Project agent settings
├── .vscode/launch.json    VS Code F5 launcher
├── AGENTS.md             Project agent guidance
├── backend/
│   ├── app/              API, database, and scheduling code
│   │   └── data/         Initial Fall 2026 catalogue
│   ├── tests/            Backend and API tests
│   └── requirements.txt  Python dependencies
├── docs/
│   ├── Report.pdf        Source timetable
│   └── assets/           Design reference and documentation images
├── frontend/
│   ├── public/           Application logo
│   ├── src/              React application
│   └── package.json      Frontend scripts and dependencies
├── main.py               Windows development launcher
└── README.md
```

The [design reference](docs/assets/referans.png) is the image used during development.

- `backend/app/data/fall_2026.json`: initial PDF catalogue for a new database.
- `backend/app/seed.py`: loads the catalogue only when the database is empty.
- `backend/app/migrations.py`: adds columns to an existing SQLite database and snapshots saved schedules.
- `backend/app/auth.py`, `backend/app/routers/admin_auth.py`, `backend/app/provision.py`: administrator sessions, visitor cookies, and account provisioning.
- `backend/app/models.py`: SQLAlchemy entities.
- `backend/app/services/scheduler.py`: constraints, search, and scoring.
- `backend/app/routers/api.py`: catalogue, preference, generation, and saved-schedule endpoints.
- `backend/app/routers/management.py`: course, section, and session CRUD endpoints.
- `backend/tests/`: catalogue, algorithm, and API tests.
- `frontend/src/components/`: six-day timetable, course management forms, preferences, alternatives, and right panel.
- `frontend/src/styles.css`: layout, colours, and grid lines.
- `frontend/public/halic-logo.png`: supplied Haliç University logo used in the app and favicon.

Run `.\.venv\Scripts\python.exe -m pytest tests -q` from `backend` and `npm run build` from `frontend`.
