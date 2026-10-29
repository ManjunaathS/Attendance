# Attendrix manual QA plan

Use a disposable test company/database and separate Employee, Manager, HR, and Admin accounts. Do not run destructive scenarios against production data. Record the browser, role, test date, expected result, actual result, and screenshot for each failure.

## Sign-in and role access

- Sign in with each role and confirm the dashboard and navigation match that role.
- Try a wrong password and an inactive account; both should remain signed out with a useful error.
- Open a manager-only or admin-only URL while signed in as Employee; access should be denied.
- As Manager, verify employee, attendance, request, and task lists contain only the assigned team.
- As Employee, verify only personal attendance, requests, and assigned tasks are visible.
- As HR, verify company-wide monitoring works and manager-only approval is blocked until delegated.
- As Admin, verify company-wide access and role/team editing.

## Attendance and location

- Office check-in with location allowed and accuracy at or below 50 m; verify time and location are saved.
- Office check-in with permission denied, missing coordinates, invalid coordinates, or accuracy above 50 m; each should be rejected.
- Open a saved check-in and check-out map icon; each should open the correct point in a new tab.
- Start and end several breaks; verify every period, monthly totals, and live worked/break totals.
- Exceed 60 minutes of total break; verify the record is visible for HR review.
- Check out and confirm its time and location appear in employee, manager, HR, and Admin attendance views.
- Attempt a second check-in, check-out during an active break, and check-in after a shift has closed; each should be rejected.
- Test shifts 1 and 2, exactly 10 minutes late, over 10 minutes late, and the fourth grace-eligible late arrival in a month.
- Request a missed-punch regularization; verify the manager can approve/reject, HR cannot decide before manager fallback, and delegated HR can decide.
- Check month selection and verify working-hour, break-hour, and per-employee totals match the underlying daily records.

## Leave, permission, and WFH

- Submit full-day leave in advance, same-day half-day leave with time range, and multi-day full-day leave.
- Verify same-day full-day leave and a past half-day request are rejected, and half-day without timing is rejected.
- Have the assigned Manager approve and reject requests; verify balances and status update once only.
- Verify HR cannot approve directly, then delegate for manager unavailability and approve/reject as HR.
- Submit permission within the 120-minute monthly allowance and beyond it; confirm the ledger outcome and balance display.
- Submit WFH in advance, approve it, then check in as WFH without location; verify unapproved/current-day WFH is rejected.
- Exceed four approved WFH days in a month and verify excess is handled as Casual Leave according to configured balance.
- Confirm WFH and permission balances remain separate from leave balances.

## Tasks, activities, content, and organization

- Assign a task to an employee; verify the assignee and assigner are shown and the assigned employee sees the assignment notification/popup.
- Update task status to In Progress, Pending with reason, and Completed; verify manager monitoring and audit history.
- Try cross-team task assignment and cross-team visibility as Manager; both should be blocked.
- Submit daily activity inside the selected shift and overlapping activity; only the valid, non-overlapping entry should save.
- Add a manager remark and verify Employee can view it while only the manager can edit it.
- Create/edit/publish a policy, news item, and event; verify Employee can view published items only.
- Create an event without a time and with several photos; verify optional time display and full-size image gallery.
- Edit team name, manager, shifts, and WFH notice; verify team membership, shift options, and manager scope update.
- As Admin/HR, update employee profile, employee number, login ID, and password; verify uniqueness checks and successful new login.
- Submit resignation as Employee; verify manager decision and HR visibility/status.

## Responsive and theme checks

- Repeat dashboard, attendance, request, employee-edit, event-editor, and approval flows at desktop, tablet, and phone widths.
- Switch light/dark theme and verify text, focus indicators, dialogs, tables, charts, and status colors remain readable.
- Check long employee names, large teams, empty states, loading states, API errors, and slow network behavior.
