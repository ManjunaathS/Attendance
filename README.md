# Attend · Company attendance and people operations

Attend is a responsive React + Tailwind interface backed by a FastAPI service and PostgreSQL. It includes individual login, role and team scoping, attendance punches and breaks, approval flows, tasks, policies, news/events with event photos, organization chart, and resignation review.

## Run the full app with Docker Compose

1. Install Docker Desktop and start it.
2. Copy `.env.example` to `.env` and set unique values for the database password, JWT secret (32+ random characters), Admin login ID, and Admin password (14+ characters).
3. From this folder run:

   ```powershell
   docker compose up --build
   ```

4. Open `http://localhost:8080`. Sign in with the Admin login from `.env`.
5. API documentation is at `http://localhost:8000/docs`.

PostgreSQL data and event media are persisted in named Docker volumes. The first API start creates tables, reference shifts/leave types, and the initial Admin account. Do not use the example credentials outside a local demo.

## Local development

Docker is optional. This Windows setup already has PostgreSQL 18 installed. Start its Windows service first: press `Win + R`, enter `services.msc`, find `postgresql-x64-18`, and choose **Start**. In pgAdmin, connect to the local server with the `postgres` password chosen during PostgreSQL installation. In the Query Tool, create the app role:

```sql
CREATE ROLE attend WITH LOGIN PASSWORD 'local_dev_change_me';
```

Then create a database owned by that role (run this as a separate query):

```sql
CREATE DATABASE attend OWNER attend;
```

If the `attend` role/database already exists, keep it and make sure the password matches `DATABASE_URL` in `.env`. Copy `.env.example` to `.env`, then run:

```powershell
cd backend
Copy-Item ..\.env .env
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
alembic upgrade head
python -m app.bootstrap
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
npm install
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). The dev proxy sends `/api/v1` requests to port 8000. Browser geolocation works on localhost or HTTPS. Office check-in/out requires location permission and an accurate location; WFH punches do not request location.

## First-time setup

To add employees, sign in as Admin or HR, open **Organization chart** in the left navigation, then choose **Add employee** at the top of the page. Create Manager accounts first, create a team and select its manager, then add employees and assign them to that team. Admin has company-wide access. Managers are scoped to their own team; HR has company-wide HR access and handles explicit manager-unavailable fallback approvals; employees see their own records. Each account has one role.

## Implemented rules

- Shift 1 09:30–18:30 and Shift 2 13:00–22:00, with 8 scheduled work hours and up to 1 hour of breaks; employees can split the break into multiple intervals.
- Office punches save browser location coordinates and reported accuracy; denied or imprecise location blocks the punch. WFH punches require approved WFH and collect no location.
- More than 10 minutes late is late; the grace-period allowance and monthly threshold are reflected in attendance rules.
- Missing checkout can be regularized with a reason and proposed time; manager approval is required before the next check-in.
- Leave, permission, and WFH are separate request types. Leave accrues 0.5 CL + 0.5 SL monthly; WFH is limited to 4 days/month; permission allowance is 2 hours/month. Manager approval is standard; HR can act on a manager step only after recorded fallback delegation.
- Managers can assign and monitor tasks. HR/Admin maintain policies; Managers/HR/Admin manage news; HR/Admin manage events/photos and the organization chart. Resignations require manager and HR review.

## Business rules to confirm before payroll use

The current WFH excess default converts approved days above 4/month to Casual Leave and requires enough CL balance. HR can change that bucket if company policy differs. The exact payroll deduction for permission beyond 2 hours when no leave remains still needs HR/Payroll confirmation before payroll integration. Configure the financial year start month and local timezone in `.env` if they differ from April and Asia/Kolkata.

## Security / production checklist

Use HTTPS, rotate the JWT secret, set secure cookies, restrict allowed origins, back up PostgreSQL and uploaded media, and review retention/consent for location data. The initial Admin is created once; provision further accounts from the protected employee management screens. HR/Admin edits and approvals are recorded in the audit log.
