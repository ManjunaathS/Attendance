# Attend — Low-Level Design

**Status:** Design draft for review  
**Scope:** Employee attendance and people operations  
**Database proposal:** PostgreSQL  

This document consolidates the requirements discussed so far. It is a design artifact, not an implementation specification signed off for production. Where a policy needs configuration or a decision was deferred, that is called out below.

## 1. Product scope

Attend provides authenticated workspaces for employees, team managers, HR, and Admin. The first release covers:

- Role-aware dashboards and employee directory / organization chart.
- Attendance punches, break tracking, monthly attendance history, location capture for office punches, and missed-punch regularization.
- Leave, permission, and work-from-home requests and balances.
- Team task assignment and progress tracking.
- Published company policies, news, and events with event photos.
- Resignation requests and approvals.
- An audit trail for approvals and sensitive changes.

## 2. Roles and authorization

Each person has an individual login ID and password and exactly one role. Admin is the exception in terms of permissions: an Admin account has all system access, but still has one role value (`ADMIN`). Roles are enforced by the server for every request; the UI only reflects those permissions.

| Role | Data scope | Main permissions |
|---|---|---|
| Employee | Own employee record | View own dashboard, attendance, balances, requests, tasks, policies, news/events, org chart, resignation status. Punch in/out and breaks, submit regularizations and time-away requests, update own task status, submit resignation. |
| Manager | Own team | View and manage team records, assign tasks, review/approve/reject team requests, manage team shifts and team settings. Can also use employee self-service for their own record. Cannot access another team’s private employee records. |
| HR | Company-wide HR scope | View and manage employee HR/attendance data across teams, handle requests when a manager is unavailable, review resignation requests, publish/edit policies and company news/events per the permissions below, and review break excess. |
| Admin | Company-wide | Full access to all modules, employee/team/role configuration, settings, and records. |

Each team has one designated manager. An employee is assigned to one team and that team determines their manager. If an employee changes teams, subsequent team-scoped access follows the new team assignment; past approvals retain the approver and team that applied at the time.

### Module permissions

| Module | Employee | Manager | HR | Admin |
|---|---|---|---|---|
| Dashboard | Own data | Own data + own team | Company-wide | Company-wide |
| Attendance | Own punches/history; submit regularization | View/manage own team; approve team regularization | Company-wide view/manage; review excess break | Full access |
| Leave, permission, WFH | View balances; submit own requests | View team; approve/reject team requests | Company-wide view; fallback approval when manager unavailable; HR administration | Full access |
| Tasks | View own; update own status | Assign and manage team tasks | View company data | Full access |
| Policies | View published | View published | Create/edit/publish | Full access |
| News | View published | Create/edit/publish | Create/edit/publish | Full access |
| Events | View | View | Create/edit/publish events and photos | Full access |
| Organization chart | View | View | Edit | Full access |
| Resignation | Submit own; view status | Review and approve/reject own team requests | Review and approve/reject; second approval required | Full access |

HR publishing of events is included as an available HR operation in this draft for consistency with HR/Admin company content management. If HR should only post news and Admin should own events, that can be narrowed in the permissions table before implementation.

## 3. Core business rules

### 3.1 Work shifts and attendance

- Shift 1 is **09:30–18:30** and is the default for the company.
- Shift 2 is **13:00–22:00** and is enabled for selected teams.
- Each shift spans 9 hours, comprising an **8-hour work target** and a **1-hour daily break allowance**.
- Teams that use both shifts can use either shift mode: manager assigns the shift in advance, or employee selects an eligible shift at check-in. The team’s shift mode and eligible shifts are stored as settings.
- The team manager assigns a team’s default shift configuration. Shift changes are versioned and date-effective so historic attendance remains associated with the shift that applied on that date.
- An employee can take multiple breaks. All break intervals are recorded; daily total is the sum of non-overlapping break intervals.
- Break time above 1 hour is measured and flagged for HR review. HR decides how any excess affects an employee’s allowance; do not automatically deduct a particular balance in this design.
- Employees choose Office or WFH at check-in. For Office check-in and check-out, precise location permission and a successful location reading are required; if permission is denied or location cannot be read, that punch is blocked. WFH punches do not request or store location.
- Record the authoritative punch timestamp on the server and preserve the client’s reported timezone for display. Store location only for Office check-in/out, together with reported accuracy. The app should clearly request location at punch time and not continuously track location.
- Late calculation uses the assigned/selected shift start. A punch more than 10 minutes after shift start is late. Each employee gets three uses per calendar month of the 10-minute grace window; after those three uses, a punch within the 10-minute window is also late. A punch more than 10 minutes late is late regardless of grace uses. A punch exactly 10 minutes after shift start is within the grace window.
- When the shift ends with no check-in, mark the employee absent. Once marked absent for that shift, block check-in for that shift. Approved leave is not an absence; approved WFH still requires attendance punches.
- Attendance summaries are shown month-wise, including work duration, total break duration, each break’s start/end/duration, status, and punch times.

### 3.2 Missed-punch regularization

- If an employee misses a punch-out, they can submit a regularization request with the date, corrected time, and reason. No submission deadline has been specified.
- A missed punch-out leaves the attendance record incomplete and blocks the employee’s next check-in until the regularization request is submitted and approved.
- The employee’s team manager approves or rejects the regularization. The decision, reason, and resulting corrected punch are audited; the original punch record is never silently overwritten.
- Manager-unavailability fallback is described in section 4. Detection criteria remain deferred.

### 3.3 Leave

- Monthly accrual is 1 day: **0.5 Casual Leave (CL)** and **0.5 Sick Leave (SL)**.
- Unused CL and SL carry forward separately month to month within the financial year.
- At financial-year end, an employee who has completed one year of service carries forward all remaining CL and SL separately. Otherwise, balances reset to zero. For this draft, eligibility is evaluated on the last day of the financial year.
- Full-day leave requests must be submitted before the leave date; same-day full-day applications are blocked. A request submitted in time may remain Pending beyond the day-before cutoff; a manager may still decide it later.
- Single-day leave can be half-day or full-day. Multi-day requests must contain full days only.
- Half-day requests may be submitted on the same day, but must be approved by the team manager before the employee’s leave begins. The employee chooses first half or second half and chooses CL or SL.
- Manager approval is normally sufficient. HR approves only when the manager is unavailable. The process must record the fallback reason and reviewer.

### 3.4 Permission

- Permission has a separate request type and a **2-hour monthly allowance**; it is tracked separately from WFH and leave balances.
- Up to 2 hours per month is without deduction. More than 2 hours may be deducted from leave in half-day increments; if no leave remains, salary deduction follows company rules.
- Requests require team manager approval; HR approves only when the manager is unavailable.
- The exact excess-duration rounding and which leave type is used are company policy choices and must be configured/confirmed before payroll integration.

### 3.5 Work from home

- WFH has a separate request module and a limit of **4 days per month**.
- Requests must be made before the requested WFH date. The team manager sets the advance-notice cutoff; the app must block requests after that cutoff.
- The team manager approves/rejects. HR approves only when the manager is unavailable.
- At attendance check-in, the employee can choose Office or WFH. WFH attendance should be accepted only when an approved WFH request covers that date. No GPS location is collected for WFH.
- WFH in excess of 4 days per month is considered leave, as initially specified. The leave type and balance handling for excess WFH needs to follow a configurable company policy; do not silently apply a deduction until that rule is confirmed.

### 3.6 Task Manager

- Managers assign tasks to employees in their own team and monitor progress.
- A task stores its title/details, assigner, assignee, due date, and status.
- Statuses are **Not started**, **In progress**, **Pending**, and **Completed**. Pending is distinct from Not started and requires a waiting reason (for example, approval or clarification).
- Employees can view their tasks and update status; managers can manage their team’s tasks.

### 3.7 Policies, news, and events

- HR and Admin create, edit, and publish policies; Employees and Managers view published policies only. Draft policies are visible to editors only.
- HR, Admin, and Managers can create, edit, publish, and view company news. Employees view published news only.
- HR/Admin create and publish past and upcoming events. Other roles can view events. Event records support one or more photos stored in object/file storage, with photo metadata and references stored in PostgreSQL.

### 3.8 Organization chart

- Display employees in team/reporting hierarchy.
- HR and Admin edit team membership, manager assignment, and reporting structure. Employees and Managers view the chart.
- A team has one designated manager; an employee has one primary team manager at a time.

### 3.9 Resignation

- An employee submits a resignation request including submission time, proposed last working day, and optional reason.
- The team manager and HR must both approve. This is a two-step approval; the request is not finally approved until both approvals are recorded.
- If the manager is unavailable, HR may perform the manager-side review as the fallback, while HR’s required review remains recorded separately. Admin may act through full access and all actions are audited.
- Employee can view status and decision history; manager sees own team requests; HR/Admin can see company-wide requests.

## 4. Approval and escalation workflow

### Manager unavailable

Normal approval routing is to the employee’s assigned team manager. When the manager is considered unavailable, route manager-level approval to HR and record `fallback_reason`, original manager, fallback reviewer, and timestamps. HR is the routine fallback approver; Admin has full access but is not the normal fallback path.

**Deferred:** How unavailability is detected (manager leave, out-of-office setting, manual reassignment, timeout, or another signal) will be decided later. Until then, provide an HR/Admin-controlled reassignment action with a required reason rather than inventing automatic detection.

### Request state model

`DRAFT → SUBMITTED → PENDING_MANAGER → APPROVED | REJECTED`

For resignation, use two approval steps:

`SUBMITTED → PENDING_MANAGER → PENDING_HR → APPROVED | REJECTED`

For fallback, the manager step is assigned to HR as a delegated review and the delegation is explicit in the approval record. A rejected request is terminal unless resubmitted as a new request or reopened by an authorized reviewer; reopening must be audited.

## 5. PostgreSQL data model

Use UUID primary keys, `timestamptz` for instants, `date` for work/request dates, and constrained enums or lookup tables for statuses. Store timestamps in UTC and render in the company/employee timezone. Apply foreign keys and indexes for every relationship and common query path.

### Identity and organization

| Table | Key fields / purpose |
|---|---|
| `users` | `id`, `employee_id` (unique), `login_id` (unique), `password_hash`, `role` (`EMPLOYEE`, `MANAGER`, `HR`, `ADMIN`), `is_active`, `last_login_at`, timestamps. Never store plaintext passwords. |
| `employees` | `id`, employee number, name, work email, phone (optional), `team_id`, employment status, join date, timezone, manager relationship derived from team, timestamps. |
| `teams` | `id`, name, `manager_employee_id`, status, timestamps. Unique/current team manager assignment. |
| `employee_team_history` | `employee_id`, `team_id`, `valid_from`, `valid_to`, `changed_by`; preserves historical team scope. |
| `team_settings` | `team_id`, shift mode (`MANAGER_ASSIGNED` or `EMPLOYEE_SELECT`), enabled shift IDs, WFH request cutoff config, effective dates. |

### Shifts and attendance

| Table | Key fields / purpose |
|---|---|
| `shifts` | `id`, name, local start/end times, timezone, target_work_minutes (480), break_allowance_minutes (60), status. Seed Shift 1 and Shift 2. |
| `employee_shift_assignments` | `id`, `employee_id`, `shift_id`, `valid_from`, `valid_to`, `assigned_by`; supports manager assignment and history. |
| `attendance_days` | `id`, `employee_id`, work date, shift ID, work mode, computed status (`PRESENT`, `LATE`, `ABSENT`, `INCOMPLETE`, etc.), total work/break minutes, late/grace result, calculation version. Unique `(employee_id, work_date)` unless multiple shifts per day are enabled later. |
| `attendance_punches` | `id`, `attendance_day_id`, type (`CHECK_IN`, `CHECK_OUT`), `occurred_at`, `recorded_at`, source, work mode, latitude/longitude and accuracy for Office only, location consent/read metadata. Punch is append-only; correction links to regularization. |
| `attendance_breaks` | `id`, `attendance_day_id`, `started_at`, `ended_at`, `start_punch_id`, `end_punch_id`, duration; supports multiple breaks, including open break. |
| `attendance_regularizations` | `id`, `employee_id`, attendance date, punch type, corrected time, reason, status, submitted/decision timestamps, manager reviewer, fallback fields, applied punch ID. |
| `monthly_late_grace_usage` | `employee_id`, year/month, qualifying grace use count; increment only for punches within 10 minutes after start, capped as allowance at three uses. Prefer derive from punches, with a transaction-safe counter or cached aggregate. |

### Leave and requests

| Table | Key fields / purpose |
|---|---|
| `leave_types` | `id`, code (`CL`, `SL`), name, enabled. |
| `leave_ledger` | `id`, employee, leave type, effective date, amount in minutes or decimal days, entry type (`ACCRUAL`, `REQUEST_DEBIT`, `CARRY_FORWARD`, `ADJUSTMENT`, `REVERSAL`), source request, note, created_by. Ledger is authoritative; balance is sum of entries. |
| `time_off_requests` | `id`, employee, type (`LEAVE`, `PERMISSION`, `WFH`), start/end dates, duration, half-day segment, leave type when applicable, reason, status, submitted_at, policy snapshot/settings version. |
| `time_off_request_days` | `request_id`, date, day fraction, approved state; represents full or half days and supports validation against calendar and monthly limits. |
| `permission_ledger` | `id`, employee, month, minutes, entry type (`ALLOWANCE`, `USED`, `EXCESS`, `ADJUSTMENT`), related request, HR decision. Separate from leave ledger. |
| `wfh_monthly_usage` | `employee_id`, year/month, approved day total; preferably derived from approved WFH request days, optionally cached. |
| `approval_steps` | `id`, request type/id, step type, assigned reviewer, assigned team, status, decided_by, decision, note, timestamps, delegated_from, fallback_reason. Generic approval history for time-off, regularization, and resignation. |

### Tasks, content, and audit

| Table | Key fields / purpose |
|---|---|
| `tasks` | `id`, team, title, description, assigned_by, assigned_to, due_at, priority, status, pending_reason, timestamps. |
| `task_status_history` | task, old/new status, reason, actor, timestamp. |
| `policies` | `id`, title, body, status (`DRAFT`, `PUBLISHED`, `ARCHIVED`), version, created_by, updated_by, published_at. |
| `news_posts` | `id`, title, body, status, author, published_at, updated_at. |
| `events` | `id`, title, description, starts_at, ends_at, location, status, author, published_at. |
| `event_media` | `id`, event_id, object key, content type, size, uploaded_by, caption/order. File bytes live in object storage, not PostgreSQL. |
| `resignation_requests` | `id`, employee_id, proposed_last_day, reason, status, submitted_at, manager/HR approval step references. |
| `audit_log` | `id`, actor user, action, entity type/id, before/after JSON, request ID, timestamp, source/IP metadata as policy permits. Append-only for application users. |
| `notifications` | recipient, event type, entity reference, channel, delivery status, created/read times. |

### Data integrity constraints

- Unique login ID and employee-to-user link; one active role per account.
- One manager per active team; a team manager must be an active account with Manager role unless Admin explicitly configures an exception.
- No overlapping active shift assignments for an employee unless multi-shift-per-day support is introduced.
- One attendance day per employee/work date in the initial model.
- Break end must be after break start; break intervals cannot overlap; check-out must follow check-in.
- Requests must not exceed available balances/allowances at approval time. Use database transactions to prevent concurrent approvals from overspending a balance.
- Event media references must belong to the event; reject unsafe content types and enforce upload size limits.
- Use soft deactivation for employees/users where audit/history must remain available; do not cascade-delete attendance or approvals.

## 6. API outline

All endpoints require authenticated HTTPS requests, server-side authorization, input validation, and an audit context. JSON API prefix: `/api/v1`.

### Authentication and profile

- `POST /auth/login` — login ID and password; return short-lived access token/session and refresh mechanism.
- `POST /auth/logout`
- `GET /me` — account, role, team, effective permissions, timezone.
- Password reset/change endpoints should use one-time expiring tokens and rate limits.

### Attendance

- `POST /attendance/check-in` — work mode, selected/assigned shift, office location payload when Office. Server validates shift mode, location, no absent/blocked state, no unresolved regularization, and no active attendance day.
- `POST /attendance/breaks/start`
- `POST /attendance/breaks/{id}/end`
- `POST /attendance/check-out` — location required for Office; closes active break only under an explicit policy (default: reject until break ended).
- `GET /attendance/me?month=YYYY-MM`
- `GET /teams/{teamId}/attendance?date=YYYY-MM-DD` — Manager only for own team; HR/Admin company scope.
- `POST /attendance/regularizations` — corrected time, punch type, reason.
- `POST /attendance/regularizations/{id}/decision` — manager decision; HR fallback only when delegated.

### Leave, permission, WFH

- `GET /time-off/me/balances?asOf=YYYY-MM-DD`
- `GET /time-off/me/requests`
- `POST /time-off/requests` — type, date(s), duration, leave type/half segment, reason. Server validates notice windows, same-day exception, full-day-only multi-day requests, WFH cutoff, and allowances.
- `GET /teams/{teamId}/requests?status=PENDING`
- `POST /requests/{id}/approval-steps/{stepId}/decision`
- `POST /requests/{id}/delegate-to-hr` — authorized reassignment with required reason.

### Tasks and content

- `GET /tasks/me`, `GET /teams/{teamId}/tasks`, `POST /teams/{teamId}/tasks`, `PATCH /tasks/{id}`.
- `GET /policies`, `POST /policies`, `PATCH /policies/{id}`, `POST /policies/{id}/publish`.
- `GET /news`, `POST /news`, `PATCH /news/{id}`, `POST /news/{id}/publish`.
- `GET /events`, `POST /events`, `PATCH /events/{id}`, `POST /events/{id}/publish`, `POST /events/{id}/media`.

### Organization and resignation

- `GET /organization/tree` — scoped view according to role.
- `PATCH /teams/{id}`, `PATCH /employees/{id}/team` — HR/Admin only; manager can edit own team’s permissible fields if configured.
- `POST /resignations`, `GET /resignations/me`, `GET /teams/{teamId}/resignations`, `POST /resignations/{id}/approval-steps/{stepId}/decision`.

### Standard response behavior

- `401` unauthenticated, `403` authenticated but outside role/team scope, `404` missing or intentionally concealed record, `409` state conflict (duplicate punch, unresolved regularization, allowance race), `422` business-rule validation failure.
- Every mutation accepts an idempotency key where retrying could create duplicate requests/punches.
- Errors return a stable code, human-readable message, and field errors without exposing sensitive data.

## 7. Key workflows

### Check in and break lifecycle

1. Employee selects Office/WFH and shift when team mode permits employee selection.
2. Server validates account/team, active shift, approved WFH request when WFH selected, unresolved missed-punch state, and absent/closed shift state.
3. Office path requests precise device location. If the location read is denied or unavailable, no punch is created. WFH path does not request location.
4. Server timestamps the punch and creates/updates `attendance_days` in one transaction.
5. Employee can start/end multiple breaks. The system records every interval and refreshes total break/work durations.
6. At shift end, absence calculation marks no-check-in employees absent and closes the check-in window. Existing approved leave is excluded.
7. At check-out, Office location is required; WFH location is omitted. Summaries and lateness are computed from server-recorded punches and effective shift configuration.

### Missed check-out

1. Attendance remains incomplete; the next check-in is blocked.
2. Employee submits corrected check-out time and reason.
3. Team manager approves/rejects; the employee cannot resume punching until approved.
4. Approval appends the corrected punch and recomputes the day. Original evidence and approval history remain auditable.

### Request approval

1. Employee submits a request; server validates current policy and available allowance.
2. Request routes to the team manager and appears in the manager’s pending queue.
3. Manager approves or rejects and supplies a note when required.
4. If manager unavailability is manually established/reassigned, HR can take the manager approval step; audit retains original manager, HR reviewer, and fallback reason.
5. On approval, ledger changes and request state are committed in one transaction; employee receives a notification.

### Resignation approval

1. Employee submits proposed last working day and optional reason.
2. Team manager review is recorded.
3. HR review is recorded as a separate required step.
4. Final status becomes Approved only after both required steps pass; HR fallback can satisfy manager review when unavailable, with explicit delegation recorded.

## 8. Security, privacy, and audit

- Passwords use a modern adaptive password hash such as Argon2id or bcrypt with per-password salt; never log or return password material.
- Use secure, HTTP-only, same-site cookies (or equivalent secure token storage), CSRF protection where applicable, rate limiting, and session revocation on account deactivation/password change.
- Enforce role and team scope in service/database query boundaries. Do not trust client-supplied employee IDs, manager IDs, roles, timestamps, leave balances, or approval status.
- Office location is collected only for check-in/check-out. Do not collect WFH GPS or background location. Restrict location access to authorized attendance viewers and define retention before launch.
- Encrypt traffic with TLS and encrypt backups/storage. Store event photo objects privately and serve via short-lived signed URLs after access checks.
- Audit role changes, employee/team/shift changes, punch corrections, approval/rejection/delegation, balance adjustments, policy edits/publishing, and event/media actions.
- Record an immutable approval trail and preserve original punch values when a correction is approved.
- Apply least privilege to database/service accounts; Admin actions are also audited.

## 9. Background jobs and derived values

- Monthly leave accrual job posts 0.5 CL and 0.5 SL per eligible employee into `leave_ledger` with a unique accrual period key to prevent duplicates.
- Financial-year closing job computes carry-forward separately for CL/SL, checks tenure as of FY end, posts carry-forward/reset ledger entries, and records the policy version used.
- Attendance calculation job closes ended shifts, marks no-check-in employees absent, computes work/break totals and late status, and detects over-break flags. It must be idempotent and re-runnable.
- WFH and permission usage reports aggregate approved requests by calendar month. All approval decisions re-check allowance within a transaction.
- Notification jobs send request submitted/decided, missed-punch block, upcoming shift, and content-published notices. Notification delivery failure must not change approval state.

## 10. Decisions still deferred / configuration required

1. **Manager-unavailability detection:** explicitly deferred. Until decided, an authorized manual delegation to HR with reason is the operational fallback.
2. **Excess break deduction:** HR reviews the measured excess and decides case by case; no automatic deduction rule yet.
3. **Excess WFH treatment:** four days is the monthly limit and excess is considered leave, but which leave bucket and behavior when no leave remains needs a configured policy.
4. **Permission excess rounding:** half-day deduction behavior is specified generally; exact minutes-to-half-day rounding and CL/SL bucket selection need policy configuration.
5. **Company financial-year boundaries/timezone and holidays:** define exact FY start/end, company timezone, holiday calendar, and weekend/working-day calendar before calculations go live.
6. **Leave one-year qualification:** draft assumes tenure is checked on the last day of the financial year, based on the example offered in the discussion.
7. **Shift selection and assignments:** both manager-assigned and employee-selected modes are supported for teams enabled for both shifts; confirm which teams use each mode and whether employee-selected shifts are chosen per day or for a schedule period.
8. **Resignation rejection order and reopening:** define whether HR may review after manager rejection and who can reopen a rejected request.
9. **Exact employee profile fields, notification channels, photo size/count limits, retention periods, payroll format, and identity/session policy.**

## 11. Suggested delivery phases

1. Finalize policy settings and acceptance criteria from section 10.
2. Implement authentication, organization/team scoping, roles, audit log, and employee directory.
3. Implement shift settings and attendance punch/break/regularization flows.
4. Implement leave, permission, WFH ledgers, requests, approvals, and notification delivery.
5. Add tasks, policies, news/events, organization chart, and resignation.
6. Build dashboards/reports and payroll export; validate all calculations against approved company examples before launch.

