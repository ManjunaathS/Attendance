"""Run end-to-end API checks against the disposable seeded E2E server."""
import http.cookiejar
import json
import os
from io import BytesIO
import urllib.error
import urllib.request
from datetime import date, timedelta
from unittest import TestCase, main
from PIL import Image

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8001/api/v1")
PASSWORD = "E2e-Test-Password-2026!"


class Client:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def call(self, method, path, body=None, expected=(200, 201, 204)):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(BASE + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            payload = error.read().decode(errors="replace")
            if error.code not in expected:
                raise AssertionError(f"{method} {path}: expected {expected}, got {error.code}: {payload}")
            return error.code, json.loads(payload) if payload.startswith("{") else payload
        raw = response.read()
        if response.status not in expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status}: {raw[:300]!r}")
        payload = json.loads(raw) if raw else None
        return response.status, payload

    def login(self, login_id):
        self.call("POST", "/auth/login", {"login_id": login_id, "password": PASSWORD})
        return self.call("GET", "/auth/me")[1]

    def upload_png(self, path, filename, content):
        boundary = "----AttendrixE2EUploadBoundary"
        payload = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: image/png\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(BASE + path, data=payload, method="POST",
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with self.opener.open(request, timeout=10) as response:
            return json.loads(response.read())


class HttpWorkflowTests(TestCase):
    def test_roles_requests_tasks_activities_content_and_resignation(self):
        employee = Client()
        employee_profile = employee.login("e2e-employee")
        self.assertEqual(employee_profile["role"], "EMPLOYEE")
        month = date.today().strftime("%Y-%m")
        for path in (
            f"/attendance/me?month={month}", f"/attendance/team?work_date={date.today().isoformat()}",
            "/attendance/config", "/attendance/regularizations", "/activities", "/time-off/balances/me",
            "/time-off/requests", "/tasks", "/policies", "/news", "/events",
            "/organization/tree", "/resignations",
        ):
            status, _ = employee.call("GET", path)
            self.assertEqual(status, 200, path)

        future = (date.today() + timedelta(days=15)).isoformat()
        _, leave = employee.call("POST", "/time-off/requests", {
            "request_type": "LEAVE", "start_date": future, "end_date": future,
            "reason": "E2E planned day off", "leave_code": "CL", "duration_days": 1,
        })
        _, permission = employee.call("POST", "/time-off/requests", {
            "request_type": "PERMISSION", "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(), "reason": "E2E appointment",
            "duration_days": 1, "permission_minutes": 150,
        })
        wfh_date = (date.today() + timedelta(days=4)).isoformat()
        _, wfh = employee.call("POST", "/time-off/requests", {
            "request_type": "WFH", "start_date": wfh_date, "end_date": wfh_date,
            "reason": "E2E home setup", "duration_days": 1,
        })
        self.assertEqual(leave["status"], "PENDING_MANAGER")

        _, activity = employee.call("POST", "/activities", {
            "activity_date": date.today().isoformat(), "shift_code": "SHIFT_1",
            "start_time": "10:00", "end_time": "11:00", "description": "E2E activity log",
        })
        self.assertEqual(activity["description"], "E2E activity log")
        # Overlapping entries must fail without storing a duplicate.
        employee.call("POST", "/activities", {
            "activity_date": date.today().isoformat(), "shift_code": "SHIFT_1",
            "start_time": "10:30", "end_time": "11:30", "description": "Overlapping test entry",
        }, expected=(409,))

        _, resignation = employee.call("POST", "/resignations", {
            "proposed_last_day": (date.today() + timedelta(days=60)).isoformat(),
            "reason": "E2E resignation workflow",
        })
        self.assertEqual(resignation["status"], "PENDING_MANAGER")

        manager = Client()
        self.assertEqual(manager.login("e2e-manager")["role"], "MANAGER")
        _, task = manager.call("POST", "/tasks", {
            "title": "E2E task assignment", "assignee_id": employee_profile["employee_id"],
            "description": "Verify employee task popup", "priority": "HIGH",
        })
        self.assertEqual(task["assignee"], "Elliot Employee")
        employee_tasks = employee.call("GET", "/tasks")[1]
        self.assertTrue(any(row["id"] == task["id"] for row in employee_tasks))
        manager.call("POST", f"/time-off/requests/{leave['id']}/decision", {"decision": "APPROVED"})
        manager.call("POST", f"/time-off/requests/{permission['id']}/decision", {"decision": "APPROVED"})
        manager.call("POST", f"/time-off/requests/{wfh['id']}/decision", {"decision": "APPROVED"})
        manager.call("PATCH", f"/activities/{activity['id']}/remark", {"remark": "Reviewed in E2E"})
        manager.call("POST", f"/resignations/{resignation['id']}/decision", {
            "step": "MANAGER", "decision": "APPROVED", "note": "E2E manager review",
        })

        hr = Client()
        self.assertEqual(hr.login("e2e-hr")["role"], "HR")
        # HR must explicitly receive manager fallback before deciding a leave request.
        _, second_leave = employee.call("POST", "/time-off/requests", {
            "request_type": "LEAVE", "start_date": future, "end_date": future,
            "reason": "E2E fallback day off", "leave_code": "SL", "duration_days": 1,
        })
        hr.call("POST", f"/time-off/requests/{second_leave['id']}/decision", {"decision": "APPROVED"}, expected=(403,))
        hr.call("POST", f"/time-off/requests/{second_leave['id']}/delegate-to-hr", {
            "reason": "E2E manager unavailable",
        })
        hr.call("POST", f"/time-off/requests/{second_leave['id']}/decision", {"decision": "APPROVED"})
        hr_activity = hr.call("GET", "/activities")[1]
        self.assertTrue(any(row["id"] == activity["id"] for row in hr_activity))

        admin = Client()
        self.assertEqual(admin.login("e2e-admin")["role"], "ADMIN")
        for path in ("/employees", "/teams", "/organization/tree", "/attendance/team", "/tasks",
                     "/policies", "/news", "/events", "/resignations"):
            status, _ = admin.call("GET", path)
            self.assertEqual(status, 200, path)
        _, event = admin.call("POST", "/events", {
            "title": "E2E optional-time event", "description": "API response keeps no-time choice",
            "starts_at": f"{wfh_date}T12:00:00", "time_unspecified": True,
            "location": "Test room", "status": "PUBLISHED",
        })
        events = admin.call("GET", "/events")[1]
        self.assertTrue(next(row for row in events if row["id"] == event["id"])["time_unspecified"])
        image = Image.new("RGB", (3, 3), color=(55, 110, 150))
        png = BytesIO()
        image.save(png, format="PNG")
        photo = admin.upload_png(f"/events/{event['id']}/media?caption=E2E+photo", "e2e.png", png.getvalue())
        image2 = Image.new("RGB", (3, 3), color=(90, 150, 90))
        png2 = BytesIO()
        image2.save(png2, format="PNG")
        photo2 = admin.upload_png(f"/events/{event['id']}/media?caption=Second+E2E+photo", "e2e-2.png", png2.getvalue())
        listed_event = next(row for row in admin.call("GET", "/events")[1] if row["id"] == event["id"])
        self.assertEqual({row["id"] for row in listed_event["photos"]}, {photo["id"], photo2["id"]})
        self.assertEqual(employee.call("GET", "/policies")[0], 200)


if __name__ == "__main__":
    main(verbosity=2)
