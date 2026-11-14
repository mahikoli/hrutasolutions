# HRUTA OneCRM — Business CRM

A full-stack CRM starter based on the HRUTA OneCRM proposal. The API uses FastAPI, SQLAlchemy 2, JWT bearer authentication and role-based access controls; the web app uses React and Vite.

## Included modules

- **CRM and sales:** leads, organizations, contacts, opportunity pipeline, stage history, proposal tracking and won-deal conversion.
- **Internships:** programs, applications, interviews, team allocations, attendance, intern tasks and certificates.
- **Training coordination:** courses, trainers, batches, enrollments, sessions, attendance, assessments, results and learner feedback. This coordinates LMS activity; it is not a replacement LMS.
- **Partnerships:** partner records, activities and agreements.
- **Projects:** project ownership, milestones, progress updates and assigned tasks.
- **Finance:** invoices, payments, balance checks, refund requests, approval and processing.
- **Workspace tools:** in-app notifications, role-aware reports and CSV exports, private record documents, workflow settings and admin audit/user-role management.
- **Foundation:** user registration and login, seeded role names, dashboard KPIs, validation and SQLAlchemy models.

External LMS/accounting/WhatsApp integrations, outbound email or messaging automation, AI features, password reset, and deployment-specific cloud file storage are not included. The proposal treats external systems as integrations to approve separately and advises against duplicating full LMS/accounting products.

File uploads are stored under the configured private upload directory (`UPLOAD_DIR`, defaults to `private_uploads/`). Allowed uploads are PDF, DOCX, XLSX, PNG and JPG, up to 10 MB each. The local SQLite database is convenient for development, not a production deployment plan.

## 1. Database

Local development uses SQLite in `hruta_onecrm.db` by default, so no database server setup is needed. To use PostgreSQL or Supabase, set `DATABASE_URL` in `.env` to a `postgresql+psycopg://...` connection string for your database.

## 2. Install and configure

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python -c "from pathlib import Path; Path('.env').touch(exist_ok=True)"
```

Add a `SECRET_KEY` with at least 32 random characters to `.env`; generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Set `DATABASE_URL` only when using PostgreSQL or Supabase; URL-encode special characters in database passwords. Supabase connection options depend on whether you use direct or pooler connections. Do not commit `.env` to GitHub.

The API uses SQLAlchemy models in `app/models.py` as its executable schema. `sql/postgresql_schema.sql` is a separate proposal design with UUID-based IDs; do not run it against the same database used by this API. Alembic manages deployed schema changes through `migrations/`.

## 3. Run

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive Swagger API documentation. Health check: `GET /health`.

## Frontend

The React frontend is the sibling folder `../frontend/`. Start it in a second terminal from the project root:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The frontend connects to the API at `http://127.0.0.1:8000/api/v1` by default. Set `VITE_API_BASE_URL` in `frontend/.env` to change it.

For local development, the app creates missing tables and seeds role names at startup (`AUTO_CREATE_SCHEMA=true`). Apply migrations from this directory with `alembic upgrade head`; set `AUTO_CREATE_SCHEMA=false` when the database schema is managed by migrations. The initial revision creates missing tables and safely adopts a database already initialized by the prior `create_all` startup. It does not rewrite existing columns. Keep that baseline immutable and make later schema changes in new reviewed Alembic revisions; autogenerate a candidate with `alembic revision --autogenerate -m "describe the change"`, review it, then apply with `alembic upgrade head`.

The hosted Render service runs `alembic upgrade head` before starting the API and disables startup `create_all`. Before production, configure TLS, hosting, backups, private object storage, and organization-approved retention controls.

## 4. Bootstrap the first administrator

Public registration intentionally assigns only `Employee / Intern`; it does not allow a caller to grant themselves admin permissions. Create a user through `/api/v1/auth/register`, then promote the first administrator through a trusted database console once, for example:

```sql
INSERT INTO user_roles (user_id, role_id)
SELECT :user_id, id FROM roles WHERE name = 'Super Admin'
ON CONFLICT DO NOTHING;
```

Use a parameterized query and replace `:user_id` with the verified account ID. Restrict access to the database console.

## Authentication

`POST /api/v1/auth/login` accepts form fields `username` (the user's email) and `password`. It returns a bearer access token. Click **Authorize** in Swagger and enter the token as prompted.

## Main API routes

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Register user |
| POST | `/api/v1/auth/login` | Obtain access token |
| GET | `/api/v1/auth/me` | Current user and roles |
| POST / GET | `/api/v1/leads` | Create/list leads; filters and pagination |
| GET / PATCH | `/api/v1/leads/{lead_id}` | View/update a lead |
| POST / GET | `/api/v1/organizations` | Create/list organizations |
| POST / GET | `/api/v1/contacts` | Create/list contacts |
| POST / GET | `/api/v1/opportunities` | Create/list sales opportunities |
| PATCH | `/api/v1/opportunities/{opportunity_id}` | Update sales stage/details |
| POST / GET | `/api/v1/activities` | Record/list calls, meetings, emails, notes |
| POST / GET | `/api/v1/tasks` | Create/list tasks; supports overdue filter |
| PATCH | `/api/v1/tasks/{task_id}` | Update task |
| GET | `/api/v1/dashboard/summary` | Role-scoped core CRM KPIs |
| POST / GET | `/api/v1/invoices` | Finance-role invoice operations |
| POST / GET | `/api/v1/payments` | Record/list payments |
| GET / POST / PATCH | `/api/v1/internships/...` | Internship programs, applications, interviews, allocations, attendance, tasks and certificates |
| GET / POST / PATCH | `/api/v1/training/...` | Courses, batches, enrollments, sessions, attendance, assessments, results and feedback |
| GET / POST / PATCH | `/api/v1/partners...`, `/api/v1/projects...` | Partnerships and project delivery |
| GET / POST / PATCH | `/api/v1/refunds...` | Finance refund workflow |
| GET / POST | `/api/v1/documents` | Upload/list private files linked to permitted CRM records |
| GET | `/api/v1/reports/summary`, `/api/v1/reports/export/{dataset}` | Role-scoped reporting and CSV export |
| GET / PATCH / PUT | `/api/v1/admin/...` | Super Admin user access, audit log and workflow settings |
| GET / POST / PATCH | `/api/v1/internship-management/...` | Student lifecycle, follow-ups, payment verification, batch confirmation, training sessions, attendance, assignments, evaluations, certificates, reports, settings and Google Form sync |

## Internship lifecycle module

The **Internship Management** workspace is integrated into the existing React shell and uses the existing internship applications, leads, trainers, notifications, private document storage, roles and audit log. Its additive Alembic revision is `20261109_0002`; apply it with `alembic upgrade head` before deploying the new API. The local development `create_all` path creates new tables but does not add the new columns to an already initialized SQLite database, so use the migration for existing databases too.

The module adds a student registration/profile API, lifecycle status history, follow-ups, payment records and verification, internship batches with capacity and roster locks, trainer assignment, training sessions and attendance, assignments and submissions, weighted final evaluations, certificate rendering/verification, data-backed overview/report endpoints, and a CSV export that opens in Excel. The main sidebar link is under the **INTERNSHIP MANAGEMENT** group. `Super Admin` and `Management` can approve unpaid batches and final evaluations. `Finance / Accounts` can verify payments. `Internship Coordinator` and `Employee / Intern` roles manage only their assigned students and coordinator-owned batches; either can claim an unassigned registration. Trainers must be linked to a CRM account with the `Trainer / Teacher` role; their APIs are limited to assigned batches.

### Google Forms / Sheets configuration

Google integration stays server-side. Set these backend environment variables; never put the API key, service-account credentials, or webhook secret in a `VITE_` variable:

```env
GOOGLE_SHEETS_SPREADSHEET_ID=your-response-spreadsheet-id
GOOGLE_SHEETS_RANGE=Form Responses 1!A:Z
GOOGLE_SHEETS_API_KEY=   # optional; works only when the response sheet is readable with the key
GOOGLE_FORM_WEBHOOK_SECRET=use-a-long-random-secret
```

For a private response sheet, configure Google Application Default Credentials for the backend service (for example, a read-only service account in `GOOGLE_APPLICATION_CREDENTIALS`) and share the response sheet with that service account. Admins can pull rows with `POST /api/v1/internship-management/sync/google-sheets`; it is safe to retry because response IDs, email and normalized mobile numbers are deduplicated. The manual sync log is available at `GET /api/v1/internship-management/sync/runs`.

For immediate form-submit sync without Google Sheets API credentials, use the spreadsheet-bound Apps Script in `integrations/google_form_webhook.gs`. Keep one master response spreadsheet and, for every new Google Form, choose that existing spreadsheet as its response destination. Google Forms adds a response tab there; the spreadsheet form-submit trigger can forward submissions from that spreadsheet. Keep question labels stable (`Name`, `Email`, `Mobile`, `College`, `Domain`) so they map to internship records. Google documents the [existing response spreadsheet option](https://support.google.com/docs/answer/2917686) and the [spreadsheet form-submit event data](https://developers.google.com/apps-script/guides/triggers/events).

Set the backend `GOOGLE_FORM_WEBHOOK_SECRET` and the Apps Script project properties `CRM_WEBHOOK_SECRET` (same value) and `CRM_WEBHOOK_URL` (`https://<backend-host>/api/v1/internship-management/sync/google-form-webhook`). Open Apps Script from the master response spreadsheet, paste `integrations/google_form_webhook.gs`, set those two script properties, then run `installCrmFormSubmitTrigger()` once and approve Google's prompt. This webhook path does not need `GOOGLE_SHEETS_API_KEY`, a service account, or `GOOGLE_SHEETS_SPREADSHEET_ID`; those are only needed for the separate manual Sheets pull. The backend rejects requests with a missing or incorrect secret, deduplicates repeated registrations by response ID/email/mobile, and places new records in Student registrations for coordinator assignment.

Certificate rendering returns a print-ready HTML certificate with a unique ID. Authorized users can print/save it as PDF, and certificate validity is available at `GET /api/v1/internship-management/public/certificates/{certificate_number}`. The student portal is not part of this CRM starter; coordinators record submissions on behalf of students unless a student-facing portal is added later.

## Important design decisions

- A lead, opportunity, contact, invoice and payment are separate records, not one combined table.
- Money uses `NUMERIC(12,2)` / `Decimal`, not floating point.
- Lists use pagination where appropriate.
- API permission checks are server-side; frontend hiding is not security.
- Finance endpoints are restricted to Finance / Accounts, Management, or Super Admin; refund decisions require Management or Super Admin.
- Non-manager users see only their own leads/opportunities and their assigned/created tasks in list endpoints.
- This is a development starter, not production-certified. Add rate limiting, password reset, refresh/revocation strategy, broader automated coverage, and organization-approved privacy/retention controls before deployment.
