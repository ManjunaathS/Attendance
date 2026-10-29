import asyncio
import unittest
from io import BytesIO
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.activities import ActivityCreate
from app.api.attendance import CheckInBody, CheckOutBody, check_in, check_out, end_break, office_location, start_break
from app.api.content import EventBody, create_event, list_events, upload_event_photo
from app.api.requests import Decision, TimeOffCreate, create_request, decide_request
from app.db import Base
from app.models import AttendanceBreak, AttendanceDay, AttendanceStatus, Employee, LeaveLedger, LeaveType, PublishStatus, RequestStatus, RequestType, Role, Shift, Team, TeamSettings, TimeOffRequest, TimeOffRequestDay, User, WorkMode


class AttendanceLocationRulesTests(unittest.TestCase):
    def test_office_punch_requires_location_coordinates_and_accuracy(self):
        with self.assertRaises(HTTPException):
            office_location(WorkMode.OFFICE, None, None, None)

    def test_office_location_accepts_accuracy_at_50_meters(self):
        office_location(WorkMode.OFFICE, 13.02347, 80.20445, 50)

    def test_office_location_rejects_accuracy_over_50_meters(self):
        with self.assertRaisesRegex(HTTPException, "50 meters or better"):
            office_location(WorkMode.OFFICE, 13.02347, 80.20445, 50.01)

    def test_office_location_rejects_invalid_coordinates(self):
        with self.assertRaisesRegex(HTTPException, "Invalid location coordinates"):
            office_location(WorkMode.OFFICE, 91, 0, 1)

    def test_wfh_does_not_require_location(self):
        office_location(WorkMode.WFH, None, None, None)


class RequestAndActivityValidationTests(unittest.TestCase):
    def test_half_day_leave_requires_timing(self):
        with self.assertRaises(ValidationError):
            TimeOffCreate(
                request_type=RequestType.LEAVE,
                start_date=date(2026, 10, 29),
                end_date=date(2026, 10, 29),
                reason="Medical appointment",
                leave_code="SL",
                duration_days=0.5,
            )


class IsolatedDatabaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        self.team = Team(name=f"Test Team {uuid4()}")
        self.db.add(self.team)
        self.db.flush()
        self.manager_employee = Employee(
            employee_number=f"M-{uuid4()}", full_name="Test Manager",
            work_email=f"manager-{uuid4()}@example.test", join_date=date(2020, 1, 1),
            team_id=self.team.id,
        )
        self.employee = Employee(
            employee_number=f"E-{uuid4()}", full_name="Test Employee",
            work_email=f"employee-{uuid4()}@example.test", join_date=date(2024, 1, 1),
            team_id=self.team.id,
        )
        self.db.add_all([self.manager_employee, self.employee])
        self.db.flush()
        self.team.manager_employee_id = self.manager_employee.id
        self.manager = User(login_id=f"manager-{uuid4()}", password_hash="not-used", role=Role.MANAGER, employee_id=self.manager_employee.id)
        self.user = User(login_id=f"employee-{uuid4()}", password_hash="not-used", role=Role.EMPLOYEE, employee_id=self.employee.id)
        self.hr = User(login_id=f"hr-{uuid4()}", password_hash="not-used", role=Role.HR)
        self.admin = User(login_id=f"admin-{uuid4()}", password_hash="not-used", role=Role.ADMIN)
        self.db.add_all([self.manager, self.user, self.hr, self.admin])
        self.shift = Shift(code=f"S-{uuid4()}", name="Test shift", starts_at=time(9, 30), ends_at=time(18, 30))
        self.db.add(self.shift)
        self.db.add(TeamSettings(team_id=self.team.id, enabled_shifts=[self.shift.code]))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_office_check_in_and_check_out_save_both_location_readings(self):
        work_day = date.today()
        mocked_now = datetime.combine(work_day, time(10), tzinfo=ZoneInfo("Asia/Kolkata"))
        with patch("app.api.attendance.local_now", return_value=mocked_now):
            check_in(
                CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                            latitude=13.02347, longitude=80.20445, accuracy_meters=24),
                self.db, self.user,
            )
            day = check_out(CheckOutBody(latitude=13.02348, longitude=80.20446, accuracy_meters=21), self.db, self.user)
        punches = {p["type"]: p for p in day["punches"]}
        self.assertEqual(punches["CHECK_IN"]["latitude"], 13.02347)
        self.assertEqual(punches["CHECK_OUT"]["longitude"], 80.20446)
        self.assertEqual(punches["CHECK_OUT"]["accuracy_meters"], 21)

    def test_break_duration_over_an_hour_flags_hr_review(self):
        work_day = date.today()
        mocked_now = datetime.combine(work_day, time(10), tzinfo=ZoneInfo("Asia/Kolkata"))
        with patch("app.api.attendance.local_now", return_value=mocked_now):
            check_in(CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                                 latitude=13.02347, longitude=80.20445, accuracy_meters=20), self.db, self.user)
            new_break = start_break(self.db, self.user)
            row = self.db.get(AttendanceBreak, UUID(new_break["id"]))
            row.started_at = datetime.now(timezone.utc) - timedelta(minutes=61)
            self.db.commit()
            ended = end_break(UUID(new_break["id"]), self.db, self.user)
        self.assertGreater(ended["total_break_minutes"], 60)
        self.assertTrue(ended["hr_review_required"])

    def test_wfh_check_in_requires_an_approved_request_for_that_day(self):
        mocked_now = datetime.combine(date.today(), time(10), tzinfo=ZoneInfo("Asia/Kolkata"))
        with patch("app.api.attendance.local_now", return_value=mocked_now):
            with self.assertRaisesRegex(HTTPException, "approved WFH request is required"):
                check_in(CheckInBody(work_mode=WorkMode.WFH, shift_code=self.shift.code), self.db, self.user)

    def test_arrivals_over_10_minutes_are_late_and_first_three_early_arrivals_use_grace(self):
        work_day = date.today()
        body = CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                           latitude=13.02347, longitude=80.20445, accuracy_meters=20)
        with patch("app.api.attendance.local_now", return_value=datetime.combine(work_day, time(9, 35), tzinfo=ZoneInfo("Asia/Kolkata"))):
            grace_result = check_in(body, self.db, self.user)
        self.assertEqual(grace_result["status"], "PRESENT")
        self.assertTrue(grace_result["grace_used"])

        # A separate employee/day ensures a 10-minute-and-one-second arrival is late.
        other = Employee(employee_number=f"E-{uuid4()}", full_name="Late Employee",
                         work_email=f"late-{uuid4()}@example.test", join_date=date(2024, 1, 1), team_id=self.team.id)
        self.db.add(other)
        self.db.flush()
        other_user = User(login_id=f"late-{uuid4()}", password_hash="not-used", role=Role.EMPLOYEE, employee_id=other.id)
        self.db.add(other_user)
        self.db.commit()
        with patch("app.api.attendance.local_now", return_value=datetime.combine(work_day, time(9, 41), tzinfo=ZoneInfo("Asia/Kolkata"))):
            late_result = check_in(body, self.db, other_user)
        self.assertEqual(late_result["status"], "LATE")

    def test_fourth_grace_eligible_arrival_in_month_is_late(self):
        today = date.today()
        for offset in (1, 2, 3):
            self.db.add(AttendanceDay(employee_id=self.employee.id, work_date=today - timedelta(days=offset),
                                      shift_id=self.shift.id, work_mode=WorkMode.OFFICE,
                                      status=AttendanceStatus.PRESENT, grace_used=True))
        self.db.commit()
        body = CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                           latitude=13.02347, longitude=80.20445, accuracy_meters=20)
        with patch("app.api.attendance.local_now", return_value=datetime.combine(today, time(9, 35), tzinfo=ZoneInfo("Asia/Kolkata"))):
            result = check_in(body, self.db, self.user)
        self.assertEqual(result["status"], "LATE")
        self.assertFalse(result["grace_used"])

    def test_check_in_after_shift_end_closes_day_as_absent_without_punch(self):
        today = date.today()
        body = CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                           latitude=13.02347, longitude=80.20445, accuracy_meters=20)
        with patch("app.api.attendance.local_now", return_value=datetime.combine(today, time(19), tzinfo=ZoneInfo("Asia/Kolkata"))):
            with self.assertRaisesRegex(HTTPException, "Shift has ended"):
                check_in(body, self.db, self.user)
        day = self.db.query(AttendanceDay).filter_by(employee_id=self.employee.id, work_date=today).one()
        self.assertEqual(day.status, AttendanceStatus.ABSENT)
        self.assertEqual(day.punches, [])

    def test_check_out_is_blocked_until_active_break_is_ended(self):
        today = date.today()
        mocked_now = datetime.combine(today, time(10), tzinfo=ZoneInfo("Asia/Kolkata"))
        body = CheckInBody(work_mode=WorkMode.OFFICE, shift_code=self.shift.code,
                           latitude=13.02347, longitude=80.20445, accuracy_meters=20)
        with patch("app.api.attendance.local_now", return_value=mocked_now):
            check_in(body, self.db, self.user)
            start_break(self.db, self.user)
            with self.assertRaisesRegex(HTTPException, "End your active break"):
                check_out(CheckOutBody(latitude=13.02348, longitude=80.20446, accuracy_meters=20), self.db, self.user)

    def test_event_optional_time_is_preserved_in_api_response(self):
        body = EventBody(title="E2E event", description="Event with no displayed time",
                         starts_at=datetime(2026, 11, 2, 12), time_unspecified=True,
                         status=PublishStatus.PUBLISHED)
        event = create_event(body, self.db, self.admin)
        self.assertEqual(event["status"], "PUBLISHED")
        listed = list_events(self.db, self.user)
        row = next(item for item in listed if item["id"] == event["id"])
        self.assertTrue(row["time_unspecified"])

    def test_event_can_store_and_list_multiple_photos(self):
        event = create_event(EventBody(title="E2E photo event", starts_at=datetime(2026, 11, 2, 12),
                                       time_unspecified=True, status=PublishStatus.PUBLISHED), self.db, self.admin)
        image = Image.new("RGB", (3, 3), color=(55, 110, 150))
        image_data = BytesIO()
        image.save(image_data, format="PNG")
        png = image_data.getvalue()
        class TestUpload:
            filename = "test.png"
            async def read(self, limit):
                return png[:limit]
        with TemporaryDirectory() as folder, patch("app.api.content.media_dir", return_value=Path(folder)):
            first = asyncio.run(upload_event_photo(UUID(event["id"]), TestUpload(), "First photo", self.db, self.admin))
            second = asyncio.run(upload_event_photo(UUID(event["id"]), TestUpload(), "Second photo", self.db, self.admin))
            row = next(item for item in list_events(self.db, self.user) if item["id"] == event["id"])
        self.assertEqual({photo["id"] for photo in row["photos"]}, {first["id"], second["id"]})

    def test_employee_leave_request_can_be_approved_by_its_assigned_manager(self):
        leave_type = LeaveType(code="CL", name="Casual Leave")
        self.db.add(leave_type)
        self.db.flush()
        future_day = date.today().fromordinal(date.today().toordinal() + 10)
        self.db.add(LeaveLedger(employee_id=self.employee.id, leave_type_id=leave_type.id,
                                effective_date=date.today(), amount_days=1, entry_type="ACCRUAL"))
        self.db.commit()
        request = create_request(
            TimeOffCreate(request_type=RequestType.LEAVE, start_date=future_day, end_date=future_day,
                          reason="Planned personal appointment", leave_code="CL", duration_days=1),
            self.db, self.user,
        )
        result = decide_request(UUID(request["id"]), Decision(decision="APPROVED", note="Approved"), self.db, self.manager)
        self.assertEqual(result["status"], "APPROVED")

    def test_hr_cannot_decide_a_request_without_manager_fallback(self):
        leave_type = LeaveType(code="CL", name="Casual Leave")
        hr = User(login_id=f"hr-{uuid4()}", password_hash="not-used", role=Role.HR)
        self.db.add_all([leave_type, hr])
        self.db.flush()
        future_day = date.today().fromordinal(date.today().toordinal() + 10)
        self.db.add(LeaveLedger(employee_id=self.employee.id, leave_type_id=leave_type.id,
                                effective_date=date.today(), amount_days=1, entry_type="ACCRUAL"))
        self.db.commit()
        request = create_request(
            TimeOffCreate(request_type=RequestType.LEAVE, start_date=future_day, end_date=future_day,
                          reason="Planned personal appointment", leave_code="CL", duration_days=1),
            self.db, self.user,
        )
        with self.assertRaisesRegex(HTTPException, "explicitly delegated"):
            decide_request(UUID(request["id"]), Decision(decision="APPROVED"), self.db, hr)

    def test_half_day_leave_accepts_period_and_timing(self):
        request = TimeOffCreate(
            request_type=RequestType.LEAVE,
            start_date=date(2026, 10, 29),
            end_date=date(2026, 10, 29),
            reason="Medical appointment",
            leave_code="SL",
            duration_days=0.5,
            half_day_period="MORNING",
            half_day_start=time(9, 30),
            half_day_end=time(13, 30),
        )
        self.assertEqual(request.duration_days, 0.5)

    def test_activity_requires_end_after_start(self):
        with self.assertRaises(ValidationError):
            ActivityCreate(
                activity_date=date(2026, 10, 28),
                shift_code="SHIFT_1",
                start_time=time(11),
                end_time=time(11),
                description="Daily work update",
            )

    def test_wfh_leave_request_requires_whole_days(self):
        with self.assertRaises(ValidationError):
            TimeOffCreate(
                request_type=RequestType.WFH,
                start_date=date(2026, 10, 30),
                end_date=date(2026, 10, 30),
                reason="Working remotely",
                duration_days=0.5,
            )


if __name__ == "__main__":
    unittest.main()
