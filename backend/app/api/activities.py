from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ActivitySheet, AttendanceDay, Employee, EmployeeShiftAssignment, Role, Shift, Team, TeamSettings, User
from ..services.audit import audit
from .auth import current_user, roles

router=APIRouter(prefix="/api/v1/activities",tags=["daily activity"])

class ActivityCreate(BaseModel):
    activity_date:date
    shift_code:str
    start_time:time
    end_time:time
    description:str=Field(min_length=3,max_length=4000)
    @model_validator(mode="after")
    def validate_time(self):
        if self.end_time<=self.start_time:raise ValueError("End time must be after start time")
        return self

class RemarkUpdate(BaseModel):
    remark:str=Field(min_length=1,max_length=4000)

def employee_for(user:User,db:Session):
    if not user.employee_id:raise HTTPException(422,"This account is not linked to an employee profile")
    e=db.get(Employee,user.employee_id)
    if not e or e.employment_status!="ACTIVE":raise HTTPException(403,"Employee account is inactive")
    return e

def assert_manager_for(user:User,employee:Employee,db:Session):
    team=db.get(Team,employee.team_id) if employee.team_id else None
    if user.role!=Role.MANAGER or not user.employee or not team or team.manager_employee_id!=user.employee.id:
        raise HTTPException(403,"Only the employee's assigned team manager can review this activity")

def activity_json(row:ActivitySheet,db:Session):
    employee=db.get(Employee,row.employee_id);shift=db.get(Shift,row.shift_id);reviewer=db.get(User,row.remarked_by) if row.remarked_by else None;team=db.get(Team,employee.team_id) if employee and employee.team_id else None;manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
    return {"id":str(row.id),"employee_id":str(row.employee_id),"employee_name":employee.full_name if employee else "","team_id":str(employee.team_id) if employee and employee.team_id else None,"team_name":team.name if team else "Unassigned","manager_id":str(manager.user.id) if manager and manager.user else None,"activity_date":row.activity_date.isoformat(),"shift_code":shift.code if shift else "","shift_name":shift.name if shift else "","shift_start":shift.starts_at.isoformat() if shift else None,"shift_end":shift.ends_at.isoformat() if shift else None,"start_time":row.start_time.isoformat(timespec="minutes"),"end_time":row.end_time.isoformat(timespec="minutes"),"description":row.description,"manager_remark":row.manager_remark,"remarked_by":reviewer.employee.full_name if reviewer and reviewer.employee else None,"remark_updated_at":row.remark_updated_at.isoformat() if row.remark_updated_at else None,"created_at":row.created_at.isoformat() if row.created_at else None}

@router.get("/config")
def activity_config(activity_date:date,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);team=db.get(Team,e.team_id) if e.team_id else None;settings=db.get(TeamSettings,team.id) if team else None
    codes=settings.enabled_shifts if settings and settings.enabled_shifts else ["SHIFT_1"]
    shifts=db.query(Shift).filter(Shift.code.in_(codes),Shift.is_active.is_(True)).order_by(Shift.starts_at).all()
    assigned=db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id==e.id,EmployeeShiftAssignment.valid_from<=activity_date).filter((EmployeeShiftAssignment.valid_to.is_(None))|(EmployeeShiftAssignment.valid_to>=activity_date)).order_by(EmployeeShiftAssignment.valid_from.desc()).first()
    if settings and settings.shift_mode.value=="MANAGER_ASSIGNED":
        if not assigned:shifts=[]
        else:shifts=[s for s in shifts if s.id==assigned.shift_id]
    attendance=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=activity_date).first()
    if attendance:shifts=[s for s in shifts if s.id==attendance.shift_id]
    return {"shifts":[{"id":str(s.id),"code":s.code,"name":s.name,"start":s.starts_at.isoformat(timespec="minutes"),"end":s.ends_at.isoformat(timespec="minutes")} for s in shifts]}

@router.get("")
def list_activities(month:str|None=None,activity_date:date|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(ActivitySheet)
    if activity_date:q=q.filter(ActivitySheet.activity_date==activity_date)
    elif month:
        try:y,m=map(int,month.split("-"));start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1)
        except (ValueError,TypeError):raise HTTPException(422,"month must be YYYY-MM")
        q=q.filter(ActivitySheet.activity_date>=start,ActivitySheet.activity_date<end)
    if user.role==Role.EMPLOYEE:q=q.filter(ActivitySheet.employee_id==user.employee_id)
    elif user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        team=db.get(Team,user.employee.team_id)
        if not team or team.manager_employee_id!=user.employee.id:raise HTTPException(403,"Manager is not assigned to this team")
        q=q.join(Employee).filter(Employee.team_id==team.id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    return [activity_json(row,db) for row in q.order_by(ActivitySheet.activity_date.desc(),ActivitySheet.start_time.asc()).limit(1000).all()]

@router.post("",status_code=201)
def create_activity(body:ActivityCreate,db:Session=Depends(get_db),user:User=Depends(roles("EMPLOYEE","MANAGER","HR","ADMIN"))):
    e=employee_for(user,db);local_today=datetime.now(timezone.utc).astimezone(ZoneInfo(e.timezone or "Asia/Kolkata")).date()
    if body.activity_date>local_today:raise HTTPException(422,"Activity date cannot be in the future")
    team=db.get(Team,e.team_id) if e.team_id else None;settings=db.get(TeamSettings,team.id) if team else None
    shift=db.query(Shift).filter_by(code=body.shift_code,is_active=True).first()
    if not shift:raise HTTPException(422,"Choose a valid shift")
    enabled=settings.enabled_shifts if settings and settings.enabled_shifts else ["SHIFT_1"]
    if shift.code not in enabled:raise HTTPException(422,"This shift is not enabled for your team")
    if settings and settings.shift_mode.value=="MANAGER_ASSIGNED":
        assignment=db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id==e.id,EmployeeShiftAssignment.valid_from<=body.activity_date).filter((EmployeeShiftAssignment.valid_to.is_(None))|(EmployeeShiftAssignment.valid_to>=body.activity_date)).order_by(EmployeeShiftAssignment.valid_from.desc()).first()
        if not assignment or assignment.shift_id!=shift.id:raise HTTPException(422,"The shift does not match your manager assignment for this date")
    attendance=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=body.activity_date).first()
    if attendance and attendance.shift_id!=shift.id:raise HTTPException(422,"Choose the shift recorded for your attendance")
    if body.start_time<shift.starts_at or body.end_time>shift.ends_at:raise HTTPException(422,f"Activity time must be within {shift.starts_at.strftime('%H:%M')}–{shift.ends_at.strftime('%H:%M')}")
    overlap=db.query(ActivitySheet).filter(ActivitySheet.employee_id==e.id,ActivitySheet.activity_date==body.activity_date,ActivitySheet.start_time<body.end_time,ActivitySheet.end_time>body.start_time).first()
    if overlap:raise HTTPException(409,"This activity time overlaps another entry for this date")
    row=ActivitySheet(employee_id=e.id,activity_date=body.activity_date,shift_id=shift.id,start_time=body.start_time,end_time=body.end_time,description=body.description)
    db.add(row);db.flush();audit(db,user,"DAILY_ACTIVITY_SUBMITTED","ActivitySheet",row.id,after={"date":body.activity_date.isoformat(),"shift":shift.code,"start":body.start_time.isoformat(),"end":body.end_time.isoformat()});db.commit();db.refresh(row)
    return activity_json(row,db)

@router.patch("/{activity_id}/remark")
def update_remark(activity_id:UUID,body:RemarkUpdate,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","ADMIN"))):
    row=db.get(ActivitySheet,activity_id)
    if not row:raise HTTPException(404,"Activity entry not found")
    employee=db.get(Employee,row.employee_id)
    if user.role==Role.MANAGER:assert_manager_for(user,employee,db)
    before=row.manager_remark;row.manager_remark=body.remark.strip();row.remarked_by=user.id;row.remark_updated_at=datetime.now(timezone.utc)
    audit(db,user,"DAILY_ACTIVITY_REMARKED","ActivitySheet",row.id,before={"remark":before},after={"remark":row.manager_remark});db.commit();db.refresh(row)
    return activity_json(row,db)
