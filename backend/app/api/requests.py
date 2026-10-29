from calendar import monthrange
from datetime import date, datetime, time, timezone
from math import ceil
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from ..db import get_db
from ..models import ApprovalStep, ApprovalStatus, Employee, LeaveLedger, LeaveType, PermissionLedger, RequestStatus, RequestType, Role, Team, TimeOffRequest, TimeOffRequestDay, User
from .auth import current_user, roles
from ..services.audit import audit

router=APIRouter(prefix="/api/v1/time-off",tags=["leave","permission","wfh","approvals"])
class TimeOffCreate(BaseModel):
    request_type:RequestType
    start_date:date
    end_date:date
    reason:str=Field(min_length=5,max_length=2000)
    leave_code:str|None=None
    duration_days:float=Field(default=1,gt=0,le=31)
    half_day_period:str|None=None
    half_day_start:time|None=None
    half_day_end:time|None=None
    permission_minutes:int|None=None
    @model_validator(mode="after")
    def check_shape(self):
        if self.end_date<self.start_date:raise ValueError("End date must be on or after start date")
        if self.request_type==RequestType.LEAVE:
            if self.leave_code not in {"CL","SL"}:raise ValueError("Choose Casual Leave (CL) or Sick Leave (SL)")
            if self.start_date!=self.end_date and self.duration_days!=int(self.duration_days):raise ValueError("Multi-day leave must use full days")
            if self.duration_days==0.5 and (not self.half_day_period or not self.half_day_start or not self.half_day_end):raise ValueError("Half-day requests require a period and start/end time")
        elif self.request_type==RequestType.PERMISSION and (not self.permission_minutes or self.permission_minutes<1):raise ValueError("Permission duration is required in minutes")
        elif self.request_type==RequestType.WFH and self.duration_days!=int(self.duration_days):raise ValueError("WFH requests must use whole days")
        return self
class Decision(BaseModel):
    decision:str
    note:str|None=None
class Delegation(BaseModel):
    reason:str=Field(min_length=5,max_length=1000)

def employee_for(user,db):
    if not user.employee_id:raise HTTPException(422,"Account is not linked to an employee profile")
    return db.get(Employee,user.employee_id)
def manager_user_id(db,e):
    team=db.get(Team,e.team_id) if e and e.team_id else None
    manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
    return str(manager.user.id) if manager and manager.user else None
def request_view(r:TimeOffRequest, db:Session):
    e=db.get(Employee,r.employee_id);leave=db.get(LeaveType,r.leave_type_id) if r.leave_type_id else None
    return {"id":str(r.id),"employee_id":str(r.employee_id),"employee_name":e.full_name if e else "","team_id":str(e.team_id) if e and e.team_id else None,"manager_id":manager_user_id(db,e),"type":r.request_type.value,"leave_code":leave.code if leave else None,"start_date":r.start_date.isoformat(),"end_date":r.end_date.isoformat(),"duration_days":r.duration_days,"half_day_period":r.half_day_period,"half_day_start":r.half_day_start.isoformat() if r.half_day_start else None,"half_day_end":r.half_day_end.isoformat() if r.half_day_end else None,"permission_minutes":r.permission_minutes,"reason":r.reason,"status":r.status.value,"manager_unavailable":r.manager_unavailable,"fallback_reason":r.fallback_reason,"submitted_at":r.submitted_at.isoformat() if r.submitted_at else None}

def leave_balance(db,eid,code,as_of):
    typ=db.query(LeaveType).filter_by(code=code).first()
    if not typ:return 0
    return float(db.query(func.coalesce(func.sum(LeaveLedger.amount_days),0)).filter(LeaveLedger.employee_id==eid,LeaveLedger.leave_type_id==typ.id,LeaveLedger.effective_date<=as_of).scalar() or 0)
def permission_used(db,eid,year_month):
    return int(db.query(func.coalesce(func.sum(PermissionLedger.minutes),0)).filter(PermissionLedger.employee_id==eid,PermissionLedger.year_month==year_month,PermissionLedger.entry_type=="USED").scalar() or 0)
def approver_for(db,e):
    team=db.get(Team,e.team_id) if e.team_id else None
    manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
    return manager.user if manager and manager.user else None

@router.get("/balances/me")
def balances(db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);today=date.today();ym=today.strftime("%Y-%m");month_start=today.replace(day=1);month_end=date(today.year+1,1,1) if today.month==12 else date(today.year,today.month+1,1)
    wfh_used=db.query(func.coalesce(func.sum(TimeOffRequestDay.day_fraction),0)).join(TimeOffRequest).filter(TimeOffRequest.employee_id==e.id,TimeOffRequest.request_type==RequestType.WFH,TimeOffRequest.status==RequestStatus.APPROVED,TimeOffRequestDay.work_date>=month_start,TimeOffRequestDay.work_date<month_end).scalar() or 0
    return {"as_of":today.isoformat(),"casual_leave_days":leave_balance(db,e.id,"CL",today),"sick_leave_days":leave_balance(db,e.id,"SL",today),"permission_minutes_used":permission_used(db,e.id,ym),"permission_minutes_remaining":max(0,120-permission_used(db,e.id,ym)),"wfh_days_used":float(wfh_used),"wfh_monthly_limit":4}
@router.get("/requests")
def list_requests(status:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(TimeOffRequest).options(selectinload(TimeOffRequest.days))
    if user.role==Role.EMPLOYEE:q=q.filter(TimeOffRequest.employee_id==user.employee_id)
    elif user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        q=q.join(Employee).filter(Employee.team_id==user.employee.team_id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    if status:q=q.filter(TimeOffRequest.status==status.upper())
    return [request_view(r,db) for r in q.order_by(TimeOffRequest.submitted_at.desc()).limit(500).all()]
@router.post("/requests",status_code=201)
def create_request(body:TimeOffCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=employee_for(user,db);today=date.today()
    if body.request_type==RequestType.LEAVE:
        if body.duration_days==1 and body.start_date<=today:raise HTTPException(422,"Full-day leave must be submitted before the leave date")
        if body.duration_days==0.5 and body.start_date<today:raise HTTPException(422,"Half-day leave must be submitted on the same day")
        typ=db.query(LeaveType).filter_by(code=body.leave_code,is_active=True).first()
        if not typ:raise HTTPException(422,"Leave type is not configured")
        if leave_balance(db,e.id,body.leave_code,body.start_date)<body.duration_days:raise HTTPException(422,"Insufficient leave balance")
    if body.request_type==RequestType.PERMISSION:
        if body.start_date<today:raise HTTPException(422,"Permission cannot be requested for a past date")
        if permission_used(db,e.id,body.start_date.strftime("%Y-%m"))+body.permission_minutes>120:
            # The request can still route for review; HR/Payroll policy decides excess deductions.
            pass
    if body.request_type==RequestType.WFH:
        if body.start_date<=today:raise HTTPException(422,"WFH must be requested before the date")
        team=db.get(Team,e.team_id) if e.team_id else None
        settings=team.settings if team else None
        cutoff=(settings.wfh_advance_notice_days if settings else 1)
        if body.start_date<today.fromordinal(today.toordinal()+cutoff):raise HTTPException(422,f"Submit WFH at least {cutoff} day(s) in advance")
        days=(body.end_date-body.start_date).days+1
        if days!=body.duration_days:raise HTTPException(422,"WFH duration must match the selected date range")
    approver=approver_for(db,e)
    req=TimeOffRequest(employee_id=e.id,request_type=body.request_type,leave_type_id=typ.id if body.request_type==RequestType.LEAVE else None,start_date=body.start_date,end_date=body.end_date,duration_days=body.duration_days,half_day_period=body.half_day_period,half_day_start=body.half_day_start,half_day_end=body.half_day_end,permission_minutes=body.permission_minutes,reason=body.reason,status=RequestStatus.PENDING_MANAGER)
    db.add(req);db.flush()
    db.add(ApprovalStep(entity_type="TIME_OFF",entity_id=req.id,step_type="MANAGER",assigned_reviewer_id=approver.id if approver else None,assigned_team_id=e.team_id,status=ApprovalStatus.PENDING))
    cursor=body.start_date
    while cursor<=body.end_date:
        fraction=body.duration_days if body.start_date==body.end_date else 1
        db.add(TimeOffRequestDay(request_id=req.id,work_date=cursor,day_fraction=fraction));cursor=cursor.fromordinal(cursor.toordinal()+1)
    audit(db,user,"TIME_OFF_SUBMITTED","TimeOffRequest",req.id,after={"type":body.request_type.value,"start":body.start_date.isoformat(),"end":body.end_date.isoformat()});db.commit();db.refresh(req)
    return request_view(req,db)
@router.post("/requests/{request_id}/delegate-to-hr")
def delegate_to_hr(request_id:UUID,body:Delegation,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR"))):
    req=db.get(TimeOffRequest,request_id)
    if not req:raise HTTPException(404,"Request not found")
    if req.status!=RequestStatus.PENDING_MANAGER:raise HTTPException(409,"Only a pending manager decision can be delegated")
    req.manager_unavailable=True;req.fallback_reason=body.reason
    step=db.query(ApprovalStep).filter_by(entity_type="TIME_OFF",entity_id=req.id,step_type="MANAGER").first()
    if step:step.status=ApprovalStatus.DELEGATED;step.delegated_from=step.assigned_reviewer_id;step.assigned_reviewer_id=None;step.fallback_reason=body.reason
    audit(db,user,"TIME_OFF_DELEGATED_TO_HR","TimeOffRequest",req.id,after={"reason":body.reason});db.commit();return request_view(req,db)
@router.post("/requests/{request_id}/decision")
def decide_request(request_id:UUID,body:Decision,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR","MANAGER"))):
    req=db.get(TimeOffRequest,request_id)
    if not req:raise HTTPException(404,"Request not found")
    if req.status!=RequestStatus.PENDING_MANAGER:raise HTTPException(409,"Request is not waiting for manager approval")
    e=db.get(Employee,req.employee_id)
    if user.role==Role.MANAGER and (not user.employee or approver_for(db,e) is None or approver_for(db,e).id!=user.id):raise HTTPException(403,"Only the assigned team manager can decide this request")
    if user.role==Role.HR and not req.manager_unavailable:raise HTTPException(403,"HR may approve only requests explicitly delegated when manager is unavailable")
    if body.decision not in {"APPROVED","REJECTED"}:raise HTTPException(422,"Decision must be APPROVED or REJECTED")
    now=datetime.now(timezone.utc);req.decided_at=now
    step=db.query(ApprovalStep).filter_by(entity_type="TIME_OFF",entity_id=req.id,step_type="MANAGER").first()
    if step:step.assigned_reviewer_id=user.id;step.status=ApprovalStatus.APPROVED if body.decision=="APPROVED" else ApprovalStatus.REJECTED;step.decision=body.decision;step.note=body.note;step.decided_at=now
    if body.decision=="REJECTED":req.status=RequestStatus.REJECTED
    else:
        if req.request_type==RequestType.LEAVE:
            typ=db.get(LeaveType,req.leave_type_id)
            if leave_balance(db,e.id,typ.code,req.start_date)<req.duration_days:raise HTTPException(409,"Leave balance changed; this request can no longer be approved")
            db.add(LeaveLedger(employee_id=e.id,leave_type_id=typ.id,effective_date=req.start_date,amount_days=-req.duration_days,entry_type="REQUEST_DEBIT",source_request_id=req.id,note="Approved leave request",created_by=user.id))
        elif req.request_type==RequestType.PERMISSION:
            ym=req.start_date.strftime("%Y-%m");already=permission_used(db,e.id,ym)
            regular=min(req.permission_minutes or 0,max(0,120-already));excess=(req.permission_minutes or 0)-regular
            if regular:db.add(PermissionLedger(employee_id=e.id,year_month=ym,minutes=regular,entry_type="USED",request_id=req.id,decided_by=user.id))
            if excess:
                half_days=ceil(excess/240)*0.5;cl=db.query(LeaveType).filter_by(code="CL").first();available=leave_balance(db,e.id,"CL",req.start_date)
                debit=min(available,half_days)
                if cl and debit:db.add(LeaveLedger(employee_id=e.id,leave_type_id=cl.id,effective_date=req.start_date,amount_days=-debit,entry_type="PERMISSION_EXCESS",source_request_id=req.id,note=f"Permission excess: {excess} minutes",created_by=user.id))
                db.add(PermissionLedger(employee_id=e.id,year_month=ym,minutes=excess,entry_type="EXCESS",request_id=req.id,decided_by=user.id,note=f"{max(0,half_days-debit)} leave day(s) exceed balance; payroll policy review required"))
        elif req.request_type==RequestType.WFH:
            cl=db.query(LeaveType).filter_by(code="CL").first()
            wfh_used_by_month={}
            for requested_day in sorted(req.days,key=lambda x:x.work_date):
                month_start=requested_day.work_date.replace(day=1)
                month_end=date(month_start.year+1,1,1) if month_start.month==12 else date(month_start.year,month_start.month+1,1)
                if month_start not in wfh_used_by_month:wfh_used_by_month[month_start]=float(db.query(func.coalesce(func.sum(TimeOffRequestDay.day_fraction),0)).join(TimeOffRequest).filter(TimeOffRequest.employee_id==e.id,TimeOffRequest.request_type==RequestType.WFH,TimeOffRequest.status==RequestStatus.APPROVED,TimeOffRequestDay.work_date>=month_start,TimeOffRequestDay.work_date<month_end).scalar() or 0)
                used=wfh_used_by_month[month_start]
                if used>=4:
                    available=leave_balance(db,e.id,"CL",requested_day.work_date)
                    if not cl or available<requested_day.day_fraction:raise HTTPException(409,f"WFH exceeds 4 days this month; {requested_day.day_fraction:g} Casual Leave day(s) are required for {requested_day.work_date.isoformat()}")
                    db.add(LeaveLedger(employee_id=e.id,leave_type_id=cl.id,effective_date=requested_day.work_date,amount_days=-requested_day.day_fraction,entry_type="WFH_EXCESS",source_request_id=req.id,note="WFH above the 4-day monthly allowance converted to Casual Leave",created_by=user.id))
                wfh_used_by_month[month_start]=used+requested_day.day_fraction
        req.status=RequestStatus.APPROVED
    audit(db,user,"TIME_OFF_"+body.decision,"TimeOffRequest",req.id,after={"note":body.note,"reviewer_role":user.role.value});db.commit();db.refresh(req);return request_view(req,db)
