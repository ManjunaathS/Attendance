from datetime import date, datetime, time
from enum import StrEnum
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, Time, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def uid(): return uuid4()
def enum_type(enum_cls): return Enum(enum_cls, native_enum=False, validate_strings=True)

class Role(StrEnum): EMPLOYEE="EMPLOYEE"; MANAGER="MANAGER"; HR="HR"; ADMIN="ADMIN"
class RequestType(StrEnum): LEAVE="LEAVE"; PERMISSION="PERMISSION"; WFH="WFH"; REGULARIZATION="REGULARIZATION"; RESIGNATION="RESIGNATION"
class RequestStatus(StrEnum): DRAFT="DRAFT"; SUBMITTED="SUBMITTED"; PENDING_MANAGER="PENDING_MANAGER"; PENDING_HR="PENDING_HR"; APPROVED="APPROVED"; REJECTED="REJECTED"; CANCELLED="CANCELLED"
class PunchType(StrEnum): CHECK_IN="CHECK_IN"; CHECK_OUT="CHECK_OUT"
class WorkMode(StrEnum): OFFICE="OFFICE"; WFH="WFH"
class AttendanceStatus(StrEnum): PRESENT="PRESENT"; LATE="LATE"; ABSENT="ABSENT"; INCOMPLETE="INCOMPLETE"; ON_LEAVE="ON_LEAVE"
class ShiftMode(StrEnum): MANAGER_ASSIGNED="MANAGER_ASSIGNED"; EMPLOYEE_SELECT="EMPLOYEE_SELECT"
class TaskStatus(StrEnum): NOT_STARTED="NOT_STARTED"; IN_PROGRESS="IN_PROGRESS"; PENDING="PENDING"; COMPLETED="COMPLETED"
class PublishStatus(StrEnum): DRAFT="DRAFT"; PUBLISHED="PUBLISHED"; ARCHIVED="ARCHIVED"
class ApprovalStatus(StrEnum): PENDING="PENDING"; APPROVED="APPROVED"; REJECTED="REJECTED"; DELEGATED="DELEGATED"; NOT_REQUIRED="NOT_REQUIRED"

class User(Base):
    __tablename__="users"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    login_id: Mapped[str]=mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[Role]=mapped_column(enum_type(Role), index=True)
    employee_id: Mapped[object|None]=mapped_column(ForeignKey("employees.id", use_alter=True, name="fk_user_employee"), unique=True)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    employee: Mapped["Employee|None"]=relationship(back_populates="user", foreign_keys=[employee_id], post_update=True)

class Team(Base):
    __tablename__="teams"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    name: Mapped[str]=mapped_column(String(120), unique=True, index=True)
    manager_employee_id: Mapped[object|None]=mapped_column(ForeignKey("employees.id"))
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    employees: Mapped[list["Employee"]]=relationship(back_populates="team", foreign_keys="Employee.team_id")
    settings: Mapped["TeamSettings|None"]=relationship(back_populates="team", uselist=False, cascade="all, delete-orphan")

class Employee(Base):
    __tablename__="employees"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_number: Mapped[str]=mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str]=mapped_column(String(180), index=True)
    work_email: Mapped[str]=mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str|None]=mapped_column(String(32))
    job_title: Mapped[str]=mapped_column(String(120), default="Employee")
    team_id: Mapped[object|None]=mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    reports_to_employee_id: Mapped[object|None]=mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    join_date: Mapped[date]=mapped_column(Date)
    timezone: Mapped[str]=mapped_column(String(64), default="Asia/Kolkata")
    employment_status: Mapped[str]=mapped_column(String(24), default="ACTIVE", index=True)
    user: Mapped[User|None]=relationship(back_populates="employee", foreign_keys=[User.employee_id], uselist=False)
    team: Mapped[Team|None]=relationship(back_populates="employees", foreign_keys=[team_id])
    manager: Mapped["Employee|None"]=relationship(remote_side="Employee.id", foreign_keys=[reports_to_employee_id])
    __table_args__=(Index("ix_employee_team_status", "team_id", "employment_status"),)

class EmployeeTeamHistory(Base):
    __tablename__="employee_team_history"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    team_id: Mapped[object]=mapped_column(ForeignKey("teams.id"))
    valid_from: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    changed_by: Mapped[object]=mapped_column(ForeignKey("users.id"))

class TeamSettings(Base):
    __tablename__="team_settings"
    team_id: Mapped[object]=mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    shift_mode: Mapped[ShiftMode]=mapped_column(enum_type(ShiftMode), default=ShiftMode.EMPLOYEE_SELECT)
    enabled_shifts: Mapped[list]=mapped_column(JSON, default=lambda:["SHIFT_1"])
    wfh_advance_notice_days: Mapped[int]=mapped_column(Integer, default=1)
    team: Mapped[Team]=relationship(back_populates="settings")

class Shift(Base):
    __tablename__="shifts"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    code: Mapped[str]=mapped_column(String(32), unique=True)
    name: Mapped[str]=mapped_column(String(80))
    starts_at: Mapped[time]=mapped_column(Time)
    ends_at: Mapped[time]=mapped_column(Time)
    target_work_minutes: Mapped[int]=mapped_column(Integer, default=480)
    break_allowance_minutes: Mapped[int]=mapped_column(Integer, default=60)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)

class EmployeeShiftAssignment(Base):
    __tablename__="employee_shift_assignments"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    shift_id: Mapped[object]=mapped_column(ForeignKey("shifts.id"))
    valid_from: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    assigned_by: Mapped[object]=mapped_column(ForeignKey("users.id"))

class AttendanceDay(Base):
    __tablename__="attendance_days"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date]=mapped_column(Date, index=True)
    shift_id: Mapped[object]=mapped_column(ForeignKey("shifts.id"))
    work_mode: Mapped[WorkMode]=mapped_column(enum_type(WorkMode))
    status: Mapped[AttendanceStatus]=mapped_column(enum_type(AttendanceStatus), default=AttendanceStatus.PRESENT, index=True)
    total_work_minutes: Mapped[int]=mapped_column(Integer, default=0)
    total_break_minutes: Mapped[int]=mapped_column(Integer, default=0)
    late_minutes: Mapped[int]=mapped_column(Integer, default=0)
    grace_used: Mapped[bool]=mapped_column(Boolean, default=False)
    calculation_version: Mapped[int]=mapped_column(Integer, default=1)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    punches: Mapped[list["AttendancePunch"]]=relationship(back_populates="attendance_day", cascade="all, delete-orphan", order_by="AttendancePunch.occurred_at")
    breaks: Mapped[list["AttendanceBreak"]]=relationship(back_populates="attendance_day", cascade="all, delete-orphan", order_by="AttendanceBreak.started_at")
    __table_args__=(UniqueConstraint("employee_id","work_date",name="uq_attendance_employee_date"),)

class AttendancePunch(Base):
    __tablename__="attendance_punches"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    attendance_day_id: Mapped[object]=mapped_column(ForeignKey("attendance_days.id", ondelete="CASCADE"), index=True)
    punch_type: Mapped[PunchType]=mapped_column(enum_type(PunchType))
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    work_mode: Mapped[WorkMode]=mapped_column(enum_type(WorkMode))
    latitude: Mapped[float|None]=mapped_column(Float)
    longitude: Mapped[float|None]=mapped_column(Float)
    accuracy_meters: Mapped[float|None]=mapped_column(Float)
    location_consent_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    attendance_day: Mapped[AttendanceDay]=relationship(back_populates="punches")
    __table_args__=(CheckConstraint("(work_mode = 'WFH' AND latitude IS NULL AND longitude IS NULL) OR (work_mode = 'OFFICE' AND latitude IS NOT NULL AND longitude IS NOT NULL)", name="ck_punch_location_by_mode"),)

class AttendanceBreak(Base):
    __tablename__="attendance_breaks"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    attendance_day_id: Mapped[object]=mapped_column(ForeignKey("attendance_days.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int]=mapped_column(Integer, default=0)
    attendance_day: Mapped[AttendanceDay]=relationship(back_populates="breaks")

class AttendanceRegularization(Base):
    __tablename__="attendance_regularizations"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    attendance_day_id: Mapped[object]=mapped_column(ForeignKey("attendance_days.id"), index=True)
    punch_type: Mapped[PunchType]=mapped_column(enum_type(PunchType))
    corrected_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    reason: Mapped[str]=mapped_column(Text)
    status: Mapped[RequestStatus]=mapped_column(enum_type(RequestStatus), default=RequestStatus.PENDING_MANAGER, index=True)
    submitted_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    decided_by: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    applied_punch_id: Mapped[object|None]=mapped_column(ForeignKey("attendance_punches.id"))
    fallback_reason: Mapped[str|None]=mapped_column(Text)

class LeaveType(Base):
    __tablename__="leave_types"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    code: Mapped[str]=mapped_column(String(12), unique=True)
    name: Mapped[str]=mapped_column(String(60))
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)

class LeaveLedger(Base):
    __tablename__="leave_ledger"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    leave_type_id: Mapped[object]=mapped_column(ForeignKey("leave_types.id"))
    effective_date: Mapped[date]=mapped_column(Date, index=True)
    amount_days: Mapped[float]=mapped_column(Float)
    entry_type: Mapped[str]=mapped_column(String(24))
    source_request_id: Mapped[object|None]=mapped_column(Uuid, index=True)
    note: Mapped[str|None]=mapped_column(Text)
    created_by: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__=(UniqueConstraint("employee_id","leave_type_id","effective_date","entry_type","source_request_id",name="uq_leave_ledger_source"),)

class TimeOffRequest(Base):
    __tablename__="time_off_requests"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    request_type: Mapped[RequestType]=mapped_column(enum_type(RequestType), index=True)
    leave_type_id: Mapped[object|None]=mapped_column(ForeignKey("leave_types.id"))
    start_date: Mapped[date]=mapped_column(Date, index=True)
    end_date: Mapped[date]=mapped_column(Date)
    duration_days: Mapped[float]=mapped_column(Float, default=1)
    half_day_period: Mapped[str|None]=mapped_column(String(24))
    half_day_start: Mapped[time|None]=mapped_column(Time)
    half_day_end: Mapped[time|None]=mapped_column(Time)
    permission_minutes: Mapped[int|None]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(Text)
    status: Mapped[RequestStatus]=mapped_column(enum_type(RequestStatus), default=RequestStatus.PENDING_MANAGER, index=True)
    manager_unavailable: Mapped[bool]=mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str|None]=mapped_column(Text)
    submitted_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    days: Mapped[list["TimeOffRequestDay"]]=relationship(back_populates="request", cascade="all, delete-orphan")

class TimeOffRequestDay(Base):
    __tablename__="time_off_request_days"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    request_id: Mapped[object]=mapped_column(ForeignKey("time_off_requests.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date]=mapped_column(Date, index=True)
    day_fraction: Mapped[float]=mapped_column(Float, default=1)
    request: Mapped[TimeOffRequest]=relationship(back_populates="days")
    __table_args__=(UniqueConstraint("request_id","work_date",name="uq_request_day"),)

class PermissionLedger(Base):
    __tablename__="permission_ledger"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    year_month: Mapped[str]=mapped_column(String(7), index=True)
    minutes: Mapped[int]=mapped_column(Integer)
    entry_type: Mapped[str]=mapped_column(String(24))
    request_id: Mapped[object|None]=mapped_column(ForeignKey("time_off_requests.id"))
    note: Mapped[str|None]=mapped_column(Text)
    decided_by: Mapped[object|None]=mapped_column(ForeignKey("users.id"))

class ApprovalStep(Base):
    __tablename__="approval_steps"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    entity_type: Mapped[str]=mapped_column(String(32), index=True)
    entity_id: Mapped[object]=mapped_column(Uuid, index=True)
    step_type: Mapped[str]=mapped_column(String(24))
    assigned_reviewer_id: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    assigned_team_id: Mapped[object|None]=mapped_column(ForeignKey("teams.id"))
    status: Mapped[ApprovalStatus]=mapped_column(enum_type(ApprovalStatus), default=ApprovalStatus.PENDING)
    decision: Mapped[str|None]=mapped_column(String(24))
    note: Mapped[str|None]=mapped_column(Text)
    submitted_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    delegated_from: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    fallback_reason: Mapped[str|None]=mapped_column(Text)

class Task(Base):
    __tablename__="tasks"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    team_id: Mapped[object]=mapped_column(ForeignKey("teams.id"), index=True)
    title: Mapped[str]=mapped_column(String(180))
    description: Mapped[str|None]=mapped_column(Text)
    assigned_by: Mapped[object]=mapped_column(ForeignKey("employees.id"))
    assigned_to: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    due_at: Mapped[date|None]=mapped_column(Date)
    priority: Mapped[str]=mapped_column(String(16), default="NORMAL")
    status: Mapped[TaskStatus]=mapped_column(enum_type(TaskStatus), default=TaskStatus.NOT_STARTED, index=True)
    pending_reason: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class TaskStatusHistory(Base):
    __tablename__="task_status_history"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    task_id: Mapped[object]=mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str|None]=mapped_column(String(24))
    new_status: Mapped[str]=mapped_column(String(24))
    reason: Mapped[str|None]=mapped_column(Text)
    actor_id: Mapped[object]=mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())

class ActivitySheet(Base):
    __tablename__="activity_sheets"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    activity_date: Mapped[date]=mapped_column(Date, index=True)
    shift_id: Mapped[object]=mapped_column(ForeignKey("shifts.id"))
    start_time: Mapped[time]=mapped_column(Time)
    end_time: Mapped[time]=mapped_column(Time)
    description: Mapped[str]=mapped_column(Text)
    manager_remark: Mapped[str|None]=mapped_column(Text)
    remarked_by: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    remark_updated_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__=(Index("ix_activity_sheet_employee_date_time","employee_id","activity_date","start_time"),CheckConstraint("end_time > start_time",name="ck_activity_sheet_time_order"))

class Policy(Base):
    __tablename__="policies"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    title: Mapped[str]=mapped_column(String(180))
    body: Mapped[str]=mapped_column(Text)
    status: Mapped[PublishStatus]=mapped_column(enum_type(PublishStatus), default=PublishStatus.DRAFT, index=True)
    version: Mapped[int]=mapped_column(Integer, default=1)
    created_by: Mapped[object]=mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[object]=mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class NewsPost(Base):
    __tablename__="news_posts"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    title: Mapped[str]=mapped_column(String(180))
    body: Mapped[str]=mapped_column(Text)
    status: Mapped[PublishStatus]=mapped_column(enum_type(PublishStatus), default=PublishStatus.DRAFT, index=True)
    author_id: Mapped[object]=mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Event(Base):
    __tablename__="events"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    title: Mapped[str]=mapped_column(String(180))
    description: Mapped[str|None]=mapped_column(Text)
    starts_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    time_unspecified: Mapped[bool]=mapped_column(Boolean, default=False, nullable=False)
    ends_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    location: Mapped[str|None]=mapped_column(String(180))
    status: Mapped[PublishStatus]=mapped_column(enum_type(PublishStatus), default=PublishStatus.DRAFT, index=True)
    author_id: Mapped[object]=mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    media: Mapped[list["EventMedia"]]=relationship(back_populates="event", cascade="all, delete-orphan")

class EventMedia(Base):
    __tablename__="event_media"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    event_id: Mapped[object]=mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str]=mapped_column(String(255), unique=True)
    content_type: Mapped[str]=mapped_column(String(80))
    size_bytes: Mapped[int]=mapped_column(Integer)
    uploaded_by: Mapped[object]=mapped_column(ForeignKey("users.id"))
    caption: Mapped[str|None]=mapped_column(String(180))
    sort_order: Mapped[int]=mapped_column(Integer, default=0)
    event: Mapped[Event]=relationship(back_populates="media")

class ResignationRequest(Base):
    __tablename__="resignation_requests"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    employee_id: Mapped[object]=mapped_column(ForeignKey("employees.id"), index=True)
    proposed_last_day: Mapped[date]=mapped_column(Date)
    reason: Mapped[str|None]=mapped_column(Text)
    status: Mapped[RequestStatus]=mapped_column(enum_type(RequestStatus), default=RequestStatus.PENDING_MANAGER, index=True)
    submitted_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class AppSetting(Base):
    __tablename__="app_settings"
    key: Mapped[str]=mapped_column(String(120), primary_key=True)
    value: Mapped[dict]=mapped_column(JSON, default=dict)
    updated_by: Mapped[object|None]=mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Notification(Base):
    __tablename__="notifications"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    recipient_id: Mapped[object]=mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str]=mapped_column(String(80))
    entity_type: Mapped[str]=mapped_column(String(60))
    entity_id: Mapped[object|None]=mapped_column(Uuid)
    message: Mapped[str]=mapped_column(String(300))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
class AuditLog(Base):
    __tablename__="audit_log"
    id: Mapped[object]=mapped_column(Uuid, primary_key=True, default=uid)
    actor_id: Mapped[object|None]=mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str]=mapped_column(String(80), index=True)
    entity_type: Mapped[str]=mapped_column(String(60), index=True)
    entity_id: Mapped[object|None]=mapped_column(Uuid, index=True)
    before_data: Mapped[dict|None]=mapped_column(JSON)
    after_data: Mapped[dict|None]=mapped_column(JSON)
    request_id: Mapped[str|None]=mapped_column(String(80))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

