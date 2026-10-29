"""Seed disposable browser-test users in the database selected by DATABASE_URL."""
from datetime import date, timedelta

from pwdlib import PasswordHash

from app.db import Base, SessionLocal, engine
from app.jobs import seed_reference_data
from app.models import (
    Employee, Event, LeaveLedger, LeaveType, NewsPost, Policy, PublishStatus,
    Role, Team, TeamSettings, User,
)

PASSWORD = "E2e-Test-Password-2026!"
Base.metadata.create_all(engine)
seed_reference_data()
db = SessionLocal()
try:
    if db.query(User).filter(User.login_id == "e2e-admin").first():
        print("E2E fixture already exists")
        raise SystemExit(0)
    hasher = PasswordHash.recommended()
    admin = User(login_id="e2e-admin", password_hash=hasher.hash(PASSWORD), role=Role.ADMIN)
    hr = User(login_id="e2e-hr", password_hash=hasher.hash(PASSWORD), role=Role.HR)
    db.add_all([admin, hr])
    db.flush()

    team = Team(name="E2E Product Team")
    db.add(team)
    db.flush()
    manager_employee = Employee(
        employee_number="E2E-MGR-001", full_name="Morgan Manager",
        work_email="morgan.manager@example.test", job_title="Team Manager",
        team_id=team.id, join_date=date(2022, 1, 1), timezone="Asia/Kolkata",
    )
    employee = Employee(
        employee_number="E2E-EMP-001", full_name="Elliot Employee",
        work_email="elliot.employee@example.test", job_title="Product Analyst",
        team_id=team.id, join_date=date(2025, 1, 1), timezone="Asia/Kolkata",
    )
    db.add_all([manager_employee, employee])
    db.flush()
    team.manager_employee_id = manager_employee.id
    db.add_all([
        TeamSettings(team_id=team.id, enabled_shifts=["SHIFT_1", "SHIFT_2"]),
        User(login_id="e2e-manager", password_hash=hasher.hash(PASSWORD), role=Role.MANAGER, employee_id=manager_employee.id),
        User(login_id="e2e-employee", password_hash=hasher.hash(PASSWORD), role=Role.EMPLOYEE, employee_id=employee.id),
    ])
    db.flush()
    month_start = date.today().replace(day=1)
    for code in ("CL", "SL"):
        leave_type = db.query(LeaveType).filter_by(code=code).one()
        db.add(LeaveLedger(employee_id=employee.id, leave_type_id=leave_type.id,
                           effective_date=month_start, amount_days=2,
                           entry_type="E2E_FIXTURE", note="Disposable browser test balance"))
    admin_user = db.query(User).filter_by(login_id="e2e-admin").one()
    db.add_all([
        Policy(title="E2E Published Policy", body="Disposable test policy", status=PublishStatus.PUBLISHED,
               created_by=admin_user.id, updated_by=admin_user.id),
        NewsPost(title="E2E Published News", body="Disposable test announcement", status=PublishStatus.PUBLISHED,
                 author_id=admin_user.id),
        Event(title="E2E Event Without Time", description="Optional-time smoke test",
              starts_at=__import__("datetime").datetime.combine(date.today() + timedelta(days=2), __import__("datetime").time(12)),
              time_unspecified=True, status=PublishStatus.PUBLISHED, author_id=admin_user.id),
    ])
    db.commit()
    print(f"Seeded disposable E2E users. Password: {PASSWORD}")
finally:
    db.close()
