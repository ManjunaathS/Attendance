from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from ..db import get_db
from ..models import AttendanceBreak, AttendanceDay, AttendancePunch, AttendanceRegularization, AttendanceStatus, Employee, EmployeeShiftAssignment, PunchType, RequestStatus, RequestType, Role, Shift, Team, TeamSettings, TimeOffRequest, TimeOffRequestDay, User, WorkMode
from .auth import current_user, roles
from ..services.audit import audit

router=APIRouter(prefix="/api/v1/attendance",tags=["attendance"])
class CheckInBody(BaseModel):
    work_mode:WorkMode
    shift_code:str
    latitude:float|None=None
    longitude:float|None=None
    accuracy_meters:float|None=None
    client_timezone:str|None=None
class CheckOutBody(BaseModel):
    latitude:float|None=None
    longitude:float|None=None
    accuracy_meters:float|None=None
class RegularizationBody(BaseModel):
    work_date:date
    punch_type:PunchType= PunchType.CHECK_OUT
    corrected_at:datetime
    reason:str=Field(min_length=5,max_length=2000)
class DecisionBody(BaseModel):
    decision:str
    note:str|None=None
class DelegationBody(BaseModel):
    reason:str=Field(min_length=5,max_length=1000)

def employee_for(user:User,db:Session):
    if not user.employee_id:raise HTTPException(422,"This account is not linked to an employee profile")
    employee=db.get(Employee,user.employee_id)
    if not employee or employee.employment_status!="ACTIVE":raise HTTPException(403,"Employee account is inactive")
    return employee

def office_location(mode:WorkMode,lat,lon,accuracy,consented=True):
    if mode==WorkMode.WFH:return
    if not consented or lat is None or lon is None or accuracy is None:raise HTTPException(422,"Precise location permission and a location reading are required for Office punches")
    if not -90<=lat<=90 or not -180<=lon<=180:raise HTTPException(422,"Invalid location coordinates")
    if accuracy>50:raise HTTPException(422,"Location accuracy must be 50 meters or better. Enable precise location and retry.")

def local_now(employee:Employee):return datetime.now(timezone.utc).astimezone(ZoneInfo(employee.timezone or "Asia/Kolkata"))
def as_utc(value:datetime):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def active_shift(employee:Employee,code:str,work_date:date,db:Session,user:User):
    team=db.get(Team,employee.team_id) if employee.team_id else None
    config=db.get(TeamSettings,employee.team_id) if employee.team_id else None
    if config and code not in (config.enabled_shifts or []):raise HTTPException(422,"This shift is not enabled for your team")
    if config and config.shift_mode.value=="MANAGER_ASSIGNED":
        assigned=db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id==employee.id,EmployeeShiftAssignment.valid_from<=work_date).filter((EmployeeShiftAssignment.valid_to.is_(None))|(EmployeeShiftAssignment.valid_to>=work_date)).order_by(EmployeeShiftAssignment.valid_from.desc()).first()
        if not assigned:raise HTTPException(422,"No shift has been assigned by your team manager")
        shift=db.get(Shift,assigned.shift_id)
        if shift.code!=code:raise HTTPException(422,"Selected shift does not match the manager assignment")
    shift=db.query(Shift).filter(Shift.code==code,Shift.is_active.is_(True)).first()
    if not shift:raise HTTPException(422,"Unknown or inactive shift")
    return shift,team

def as_dict(day:AttendanceDay):
    now=datetime.now(timezone.utc)
    punch_in=next((p for p in day.punches if p.punch_type==PunchType.CHECK_IN),None)
    punch_out=next((p for p in day.punches if p.punch_type==PunchType.CHECK_OUT),None)
    break_rows=[];break_total=0
    for br in day.breaks:
        duration=br.duration_minutes if br.duration_minutes is not None else max(0,int((as_utc(br.ended_at or now)-as_utc(br.started_at)).total_seconds()//60))
        break_total+=duration
        break_rows.append({"id":str(br.id),"start":br.started_at.isoformat(),"end":br.ended_at.isoformat() if br.ended_at else None,"duration_minutes":duration})
    work_total=day.total_work_minutes
    if punch_in and not punch_out:
        work_total=max(0,int((as_utc(now)-as_utc(punch_in.occurred_at)).total_seconds()//60)-break_total)
    return {"id":str(day.id),"date":day.work_date.isoformat(),"shift_id":str(day.shift_id),"work_mode":day.work_mode.value,"status":day.status.value,"work_minutes":work_total,"break_minutes":break_total,"late_minutes":day.late_minutes,"grace_used":day.grace_used,"punches":[{"id":str(p.id),"type":p.punch_type.value,"at":p.occurred_at.isoformat(),"latitude":p.latitude,"longitude":p.longitude,"accuracy_meters":p.accuracy_meters} for p in day.punches],"breaks":break_rows}

@router.post("/check-in",status_code=201)
def check_in(body:CheckInBody,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db); now=local_now(e); work_date=now.date()
    office_location(body.work_mode,body.latitude,body.longitude,body.accuracy_meters)
    shift,team=active_shift(e,body.shift_code,work_date,db,user)
    if now.time()>=shift.ends_at:
        day=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=work_date).first()
        if not day:
            day=AttendanceDay(employee_id=e.id,work_date=work_date,shift_id=shift.id,work_mode=body.work_mode,status=AttendanceStatus.ABSENT);db.add(day);db.commit()
        raise HTTPException(409,"Shift has ended; this shift is closed for check-in.")
    existing=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=work_date).first()
    if existing:raise HTTPException(409,"An attendance record already exists for this shift/date")
    unresolved=db.query(AttendanceRegularization).filter_by(employee_id=e.id,status=RequestStatus.PENDING_MANAGER).first()
    if unresolved:raise HTTPException(409,"Check-in is locked until your missed-punch request is decided")
    if body.work_mode==WorkMode.WFH:
        approved=db.query(TimeOffRequestDay).join(TimeOffRequest).filter(TimeOffRequest.employee_id==e.id,TimeOffRequest.request_type=="WFH",TimeOffRequest.status==RequestStatus.APPROVED,TimeOffRequestDay.work_date==work_date).first()
        if not approved:raise HTTPException(422,"An approved WFH request is required for this date")
    start=datetime.combine(work_date,shift.starts_at,tzinfo=ZoneInfo(e.timezone or "Asia/Kolkata"))
    minutes_late=max(0,int((now-start).total_seconds()//60))
    grace_used=False; status=AttendanceStatus.PRESENT
    if minutes_late>10:status=AttendanceStatus.LATE
    elif minutes_late>0:
        month_start=work_date.replace(day=1)
        used=db.query(func.count(AttendanceDay.id)).filter(AttendanceDay.employee_id==e.id,AttendanceDay.work_date>=month_start,AttendanceDay.work_date<=work_date,AttendanceDay.grace_used.is_(True)).scalar() or 0
        if used<3:grace_used=True
        else:status=AttendanceStatus.LATE
    day=AttendanceDay(employee_id=e.id,work_date=work_date,shift_id=shift.id,work_mode=body.work_mode,status=status,late_minutes=minutes_late,grace_used=grace_used)
    db.add(day);db.flush()
    punch=AttendancePunch(attendance_day_id=day.id,punch_type=PunchType.CHECK_IN,occurred_at=datetime.now(timezone.utc),work_mode=body.work_mode,latitude=body.latitude if body.work_mode==WorkMode.OFFICE else None,longitude=body.longitude if body.work_mode==WorkMode.OFFICE else None,accuracy_meters=body.accuracy_meters if body.work_mode==WorkMode.OFFICE else None,location_consent_at=datetime.now(timezone.utc) if body.work_mode==WorkMode.OFFICE else None)
    db.add(punch);audit(db,user,"ATTENDANCE_CHECK_IN","AttendanceDay",day.id,after={"work_mode":body.work_mode.value,"shift_code":body.shift_code,"status":status.value});db.commit();db.refresh(day)
    return as_dict(day)

@router.post("/check-out")
def check_out(body:CheckOutBody,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);now=datetime.now(timezone.utc);today=local_now(e).date()
    day=db.query(AttendanceDay).options(selectinload(AttendanceDay.punches),selectinload(AttendanceDay.breaks)).filter_by(employee_id=e.id,work_date=today).first()
    if not day:raise HTTPException(409,"No active attendance record")
    if day.status==AttendanceStatus.ABSENT:raise HTTPException(409,"Shift is absent/closed")
    office_location(day.work_mode,body.latitude,body.longitude,body.accuracy_meters)
    if any(b.ended_at is None for b in day.breaks):raise HTTPException(409,"End your active break before checking out")
    if any(p.punch_type==PunchType.CHECK_OUT for p in day.punches):raise HTTPException(409,"Already checked out")
    punchin=next((p for p in day.punches if p.punch_type==PunchType.CHECK_IN),None)
    if not punchin:raise HTTPException(409,"Check-in is missing")
    punch=AttendancePunch(attendance_day_id=day.id,punch_type=PunchType.CHECK_OUT,occurred_at=now,work_mode=day.work_mode,latitude=body.latitude if day.work_mode==WorkMode.OFFICE else None,longitude=body.longitude if day.work_mode==WorkMode.OFFICE else None,accuracy_meters=body.accuracy_meters if day.work_mode==WorkMode.OFFICE else None,location_consent_at=now if day.work_mode==WorkMode.OFFICE else None)
    db.add(punch);day.total_work_minutes=max(0,int((as_utc(now)-as_utc(punchin.occurred_at)).total_seconds()//60)-day.total_break_minutes);db.commit();db.refresh(day)
    return as_dict(day)

@router.post("/breaks/start",status_code=201)
def start_break(db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);day=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=local_now(e).date()).first()
    if not day or day.status==AttendanceStatus.ABSENT:raise HTTPException(409,"No active attendance record")
    if any(b.ended_at is None for b in day.breaks):raise HTTPException(409,"A break is already active")
    if any(p.punch_type==PunchType.CHECK_OUT for p in day.punches):raise HTTPException(409,"Already checked out")
    br=AttendanceBreak(attendance_day_id=day.id,started_at=datetime.now(timezone.utc));db.add(br);db.commit();db.refresh(br)
    return {"id":str(br.id),"started_at":br.started_at.isoformat()}
@router.post("/breaks/{break_id}/end")
def end_break(break_id:UUID,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);br=db.query(AttendanceBreak).join(AttendanceDay).filter(AttendanceBreak.id==break_id,AttendanceDay.employee_id==e.id).first()
    if not br or br.ended_at:raise HTTPException(404,"Open break not found")
    br.ended_at=datetime.now(timezone.utc);br.duration_minutes=max(0,int((as_utc(br.ended_at)-as_utc(br.started_at)).total_seconds()//60));br.attendance_day.total_break_minutes=sum(b.duration_minutes for b in br.attendance_day.breaks if b.id!=br.id)+br.duration_minutes
    if br.attendance_day.total_break_minutes>60:br.attendance_day.status=br.attendance_day.status
    db.commit();return {"id":str(br.id),"duration_minutes":br.duration_minutes,"total_break_minutes":br.attendance_day.total_break_minutes,"hr_review_required":br.attendance_day.total_break_minutes>60}

@router.get("/me")
def my_attendance(month:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db)
    try:y,m=map(int,month.split("-"));start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1)
    except (ValueError,TypeError):raise HTTPException(422,"month must be YYYY-MM")
    days=db.query(AttendanceDay).options(selectinload(AttendanceDay.punches),selectinload(AttendanceDay.breaks)).filter(AttendanceDay.employee_id==e.id,AttendanceDay.work_date>=start,AttendanceDay.work_date<end).order_by(AttendanceDay.work_date).all()
    return [as_dict(d) for d in days]
@router.get("/team")
def team_attendance(work_date:date|None=None,month:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(AttendanceDay).options(selectinload(AttendanceDay.punches),selectinload(AttendanceDay.breaks))
    if work_date:q=q.filter(AttendanceDay.work_date==work_date)
    elif month:
        try:y,m=map(int,month.split("-"));start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1)
        except (ValueError,TypeError):raise HTTPException(422,"month must be YYYY-MM")
        q=q.filter(AttendanceDay.work_date>=start,AttendanceDay.work_date<end)
    if user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:raise HTTPException(403,"Manager is not assigned to a team")
        q=q.join(Employee).filter(Employee.team_id==user.employee.team_id)
    elif user.role==Role.EMPLOYEE:q=q.filter(AttendanceDay.employee_id==user.employee_id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    ordered=q.order_by(AttendanceDay.work_date.desc())
    days=ordered.all() if month else ordered.limit(500).all()
    employees={e.id:e for e in db.query(Employee).filter(Employee.id.in_({d.employee_id for d in days})).all()} if days else {}
    return [{**as_dict(d),"employee_id":str(d.employee_id),"employee_name":employees[d.employee_id].full_name if d.employee_id in employees else "Employee","team_id":str(employees[d.employee_id].team_id) if d.employee_id in employees and employees[d.employee_id].team_id else None} for d in days]
@router.post("/regularizations",status_code=201)
def regularize(body:RegularizationBody,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);day=db.query(AttendanceDay).filter_by(employee_id=e.id,work_date=body.work_date).first()
    if not day:raise HTTPException(404,"Attendance record not found")
    if db.query(AttendanceRegularization).filter_by(employee_id=e.id,attendance_day_id=day.id,status=RequestStatus.PENDING_MANAGER).first():raise HTTPException(409,"A regularization is already waiting for approval")
    req=AttendanceRegularization(employee_id=e.id,attendance_day_id=day.id,punch_type=body.punch_type,corrected_at=body.corrected_at,reason=body.reason,status=RequestStatus.PENDING_MANAGER)
    day.status=AttendanceStatus.INCOMPLETE;db.add(req);db.flush();audit(db,user,"REGULARIZATION_SUBMITTED","AttendanceRegularization",req.id,after={"corrected_at":body.corrected_at.isoformat(),"reason":body.reason});db.commit();return {"id":str(req.id),"status":req.status.value}
@router.get("/regularizations")
def list_regularizations(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(AttendanceRegularization)
    if user.role==Role.EMPLOYEE:q=q.filter(AttendanceRegularization.employee_id==user.employee_id)
    elif user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        q=q.join(Employee).filter(Employee.team_id==user.employee.team_id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    result=[]
    for r in q.order_by(AttendanceRegularization.submitted_at.desc()).all():
        e=db.get(Employee,r.employee_id); team=db.get(Team,e.team_id) if e and e.team_id else None; manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
        result.append({"id":str(r.id),"employee_id":str(r.employee_id),"employee_name":e.full_name if e else "","team_id":str(e.team_id) if e and e.team_id else None,"manager_id":str(manager.user.id) if manager and manager.user else None,"date":r.corrected_at.date().isoformat(),"corrected_at":r.corrected_at.isoformat(),"reason":r.reason,"status":r.status.value,"fallback_reason":r.fallback_reason})
    return result
@router.post("/regularizations/{request_id}/delegate-to-hr")
def delegate_regularization(request_id:UUID,body:DelegationBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    req=db.get(AttendanceRegularization,request_id)
    if not req or req.status!=RequestStatus.PENDING_MANAGER:raise HTTPException(404,"Open manager step not found")
    req.fallback_reason=body.reason;audit(db,user,"REGULARIZATION_DELEGATED_TO_HR","AttendanceRegularization",req.id,after={"reason":body.reason});db.commit()
    return {"id":str(req.id),"status":req.status.value,"fallback_reason":req.fallback_reason}
@router.post("/regularizations/{request_id}/decision")
def decide_regularization(request_id:UUID,body:DecisionBody,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","HR","ADMIN"))):
    req=db.query(AttendanceRegularization).filter_by(id=request_id).first()
    if not req:raise HTTPException(404,"Regularization not found")
    e=db.get(Employee,req.employee_id)
    if user.role==Role.MANAGER and (not user.employee or not e.team_id or not db.get(Team,e.team_id) or db.get(Team,e.team_id).manager_employee_id!=user.employee.id):raise HTTPException(403,"Only the assigned team manager can decide this regularization")
    if user.role==Role.HR and not req.fallback_reason:raise HTTPException(403,"HR fallback requires an explicit delegation reason")
    if req.status!=RequestStatus.PENDING_MANAGER:raise HTTPException(409,"Request already decided")
    now=datetime.now(timezone.utc);req.decided_by=user.id;req.decided_at=now
    day=db.get(AttendanceDay,req.attendance_day_id)
    if body.decision.upper()=="APPROVED":
        punch=AttendancePunch(attendance_day_id=day.id,punch_type=req.punch_type,occurred_at=req.corrected_at,recorded_at=now,work_mode=day.work_mode);db.add(punch);db.flush();req.applied_punch_id=punch.id;req.status=RequestStatus.APPROVED;day.status=AttendanceStatus.PRESENT
    elif body.decision.upper()=="REJECTED":req.status=RequestStatus.REJECTED;day.status=AttendanceStatus.INCOMPLETE
    else:raise HTTPException(422,"Decision must be Approved or Rejected")
    audit(db,user,"REGULARIZATION_"+body.decision.upper(),"AttendanceRegularization",req.id,after={"note":body.note});db.commit();return {"id":str(req.id),"status":req.status.value}

@router.get("/config")
def attendance_config(db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);team=db.get(Team,e.team_id) if e.team_id else None;cfg=db.get(TeamSettings,team.id) if team else None
    shifts=db.query(Shift).filter(Shift.code.in_(cfg.enabled_shifts if cfg and cfg.enabled_shifts else ["SHIFT_1"]),Shift.is_active.is_(True)).order_by(Shift.starts_at).all()
    today=local_now(e).date();wfh=db.query(TimeOffRequestDay).join(TimeOffRequest).filter(TimeOffRequest.employee_id==e.id,TimeOffRequest.request_type==RequestType.WFH,TimeOffRequest.status==RequestStatus.APPROVED,TimeOffRequestDay.work_date==today).first()
    assigned=db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id==e.id,EmployeeShiftAssignment.valid_from<=today).filter((EmployeeShiftAssignment.valid_to.is_(None))|(EmployeeShiftAssignment.valid_to>=today)).order_by(EmployeeShiftAssignment.valid_from.desc()).first()
    assigned_shift=db.get(Shift,assigned.shift_id) if assigned else None
    return {"shift_mode":cfg.shift_mode.value if cfg else "EMPLOYEE_SELECT","shifts":[{"id":str(s.id),"code":s.code,"name":s.name,"start":s.starts_at.isoformat(),"end":s.ends_at.isoformat()} for s in shifts],"assigned_shift_code":assigned_shift.code if assigned_shift else None,"wfh_approved_today":bool(wfh),"office_location_accuracy_limit_meters":50,"target_work_minutes":480,"break_allowance_minutes":60}
