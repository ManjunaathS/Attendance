from datetime import date, datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ApprovalStep, ApprovalStatus, Employee, EmployeeTeamHistory, ResignationRequest, RequestStatus, Role, Team, TeamSettings, User
from .auth import current_user, roles
from ..services.audit import audit

router=APIRouter(prefix="/api/v1",tags=["organization","resignation"])
class TeamUpdate(BaseModel):
    name:str|None=None
    manager_employee_id:UUID|None=None
    shift_mode:str|None=None
    enabled_shifts:list[str]|None=None
    wfh_advance_notice_days:int|None=Field(default=None,ge=0,le=90)
class TeamMove(BaseModel):
    team_id:UUID|None
    reports_to_employee_id:UUID|None=None
    effective_date:date=date.today()
class ResignationCreate(BaseModel):
    proposed_last_day:date
    reason:str|None=None
class ResignationDecision(BaseModel):
    step:str
    decision:str
    note:str|None=None
class FallbackBody(BaseModel):
    reason:str=Field(min_length=5,max_length=1000)

@router.get("/organization/tree")
def organization_tree(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Employee).filter(Employee.employment_status=="ACTIVE")
    if user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return {"teams":[]}
        q=q.filter(Employee.team_id==user.employee.team_id)
    elif user.role==Role.EMPLOYEE:
        # Public directory fields only; no private contact or attendance data are exposed.
        pass
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    employees=q.order_by(Employee.full_name).all();teams={}
    for e in employees:
        key=str(e.team_id) if e.team_id else "unassigned"
        item=teams.setdefault(key,{"team_id":key,"team_name":e.team.name if e.team else "Unassigned","manager_employee_id":str(e.team.manager_employee_id) if e.team and e.team.manager_employee_id else None,"members":[]})
        item["members"].append({"id":str(e.id),"name":e.full_name,"job_title":e.job_title,"reports_to_employee_id":str(e.reports_to_employee_id) if e.reports_to_employee_id else None,"is_manager":bool(e.team and e.team.manager_employee_id==e.id)})
    return {"teams":list(teams.values())}
@router.patch("/teams/{team_id}")
def update_team(team_id:UUID,body:TeamUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    team=db.get(Team,team_id)
    if not team:raise HTTPException(404,"Team not found")
    if user.role==Role.MANAGER:
        if not user.employee or user.employee.team_id!=team.id:raise HTTPException(403,"Outside your team")
        if body.manager_employee_id is not None or body.name is not None:raise HTTPException(403,"Managers can adjust only their team settings")
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    if "manager_employee_id" in body.model_fields_set:
        if body.manager_employee_id is None:team.manager_employee_id=None
        else:
            m=db.get(Employee,body.manager_employee_id)
            if not m or not m.user or m.user.role!=Role.MANAGER:raise HTTPException(422,"Team manager must have an active Manager account")
            if m.team_id and m.team_id!=team.id:raise HTTPException(409,"This Manager is already assigned to another team")
            team.manager_employee_id=m.id
            m.team_id=team.id
    if body.name is not None:team.name=body.name
    cfg=team.settings or TeamSettings(team_id=team.id)
    if body.shift_mode is not None:cfg.shift_mode=body.shift_mode
    if body.enabled_shifts is not None:cfg.enabled_shifts=body.enabled_shifts
    if body.wfh_advance_notice_days is not None:cfg.wfh_advance_notice_days=body.wfh_advance_notice_days
    db.add(cfg);audit(db,user,"TEAM_SETTINGS_UPDATED","Team",team.id,after=body.model_dump(exclude_none=True));db.commit();return {"id":str(team.id),"name":team.name,"manager_employee_id":str(team.manager_employee_id) if team.manager_employee_id else None,"shift_mode":cfg.shift_mode.value,"enabled_shifts":cfg.enabled_shifts,"wfh_advance_notice_days":cfg.wfh_advance_notice_days}
@router.patch("/employees/{employee_id}/team")
def move_employee(employee_id:UUID,body:TeamMove,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR"))):
    e=db.get(Employee,employee_id)
    if not e:raise HTTPException(404,"Employee not found")
    if body.team_id and not db.get(Team,body.team_id):raise HTTPException(404,"Team not found")
    if e.team_id!=body.team_id:
        if e.team_id:db.add(EmployeeTeamHistory(employee_id=e.id,team_id=e.team_id,valid_from=e.join_date,valid_to=body.effective_date,changed_by=user.id))
        e.team_id=body.team_id
    e.reports_to_employee_id=body.reports_to_employee_id;audit(db,user,"EMPLOYEE_TEAM_CHANGED","Employee",e.id,after={"team_id":str(body.team_id) if body.team_id else None,"reports_to":str(body.reports_to_employee_id) if body.reports_to_employee_id else None});db.commit();return {"id":str(e.id),"team_id":str(e.team_id) if e.team_id else None}

def manager_user_id(db,e):
    team=db.get(Team,e.team_id) if e and e.team_id else None
    manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
    return str(manager.user.id) if manager and manager.user else None
def resignation_json(r:ResignationRequest,db:Session):
    e=db.get(Employee,r.employee_id);steps=db.query(ApprovalStep).filter_by(entity_type="RESIGNATION",entity_id=r.id).order_by(ApprovalStep.submitted_at).all()
    return {"id":str(r.id),"employee_id":str(r.employee_id),"employee_name":e.full_name if e else "","team_id":str(e.team_id) if e and e.team_id else None,"manager_id":manager_user_id(db,e),"proposed_last_day":r.proposed_last_day.isoformat(),"reason":r.reason,"status":r.status.value,"submitted_at":r.submitted_at.isoformat() if r.submitted_at else None,"approvals":[{"step":s.step_type,"status":s.status.value,"decision":s.decision,"note":s.note,"fallback_reason":s.fallback_reason,"decided_at":s.decided_at.isoformat() if s.decided_at else None} for s in steps]}
@router.post("/resignations",status_code=201)
def submit_resignation(body:ResignationCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not user.employee_id:raise HTTPException(422,"Account is not linked to an employee")
    if body.proposed_last_day<=date.today():raise HTTPException(422,"Last working day must be in the future")
    active=db.query(ResignationRequest).filter(ResignationRequest.employee_id==user.employee_id,ResignationRequest.status.in_([RequestStatus.PENDING_MANAGER,RequestStatus.PENDING_HR])).first()
    if active:raise HTTPException(409,"You already have a resignation request under review")
    e=db.get(Employee,user.employee_id);team=db.get(Team,e.team_id) if e.team_id else None;manager=db.get(Employee,team.manager_employee_id) if team and team.manager_employee_id else None
    r=ResignationRequest(employee_id=e.id,proposed_last_day=body.proposed_last_day,reason=body.reason,status=RequestStatus.PENDING_MANAGER);db.add(r);db.flush()
    db.add(ApprovalStep(entity_type="RESIGNATION",entity_id=r.id,step_type="MANAGER",assigned_reviewer_id=manager.user.id if manager and manager.user else None,assigned_team_id=e.team_id,status=ApprovalStatus.PENDING))
    db.add(ApprovalStep(entity_type="RESIGNATION",entity_id=r.id,step_type="HR",status=ApprovalStatus.PENDING))
    audit(db,user,"RESIGNATION_SUBMITTED","ResignationRequest",r.id,after={"proposed_last_day":body.proposed_last_day.isoformat()});db.commit();db.refresh(r);return resignation_json(r,db)
@router.get("/resignations")
def list_resignations(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(ResignationRequest)
    if user.role==Role.EMPLOYEE:q=q.filter(ResignationRequest.employee_id==user.employee_id)
    elif user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        q=q.join(Employee).filter(Employee.team_id==user.employee.team_id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    return [resignation_json(r,db) for r in q.order_by(ResignationRequest.submitted_at.desc()).all()]
@router.post("/resignations/{request_id}/delegate-to-hr")
def delegate_resignation(request_id:UUID,body:FallbackBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    r=db.get(ResignationRequest,request_id)
    if not r or r.status!=RequestStatus.PENDING_MANAGER:raise HTTPException(404,"Open manager step not found")
    step=db.query(ApprovalStep).filter_by(entity_type="RESIGNATION",entity_id=r.id,step_type="MANAGER").first()
    if step:step.status=ApprovalStatus.DELEGATED;step.delegated_from=step.assigned_reviewer_id;step.fallback_reason=body.reason;step.assigned_reviewer_id=None
    audit(db,user,"RESIGNATION_MANAGER_STEP_DELEGATED","ResignationRequest",r.id,after={"reason":body.reason});db.commit();return resignation_json(r,db)
@router.post("/resignations/{request_id}/decision")
def decide_resignation(request_id:UUID,body:ResignationDecision,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","HR","ADMIN"))):
    r=db.get(ResignationRequest,request_id)
    if not r:raise HTTPException(404,"Resignation request not found")
    if body.decision not in {"APPROVED","REJECTED"}:raise HTTPException(422,"Decision must be APPROVED or REJECTED")
    e=db.get(Employee,r.employee_id)
    if body.step=="MANAGER":
        step=db.query(ApprovalStep).filter_by(entity_type="RESIGNATION",entity_id=r.id,step_type="MANAGER").first()
        if user.role==Role.MANAGER and (not step or step.assigned_reviewer_id!=user.id):raise HTTPException(403,"Only the assigned team manager can decide this resignation")
        if user.role==Role.HR and (not step or step.status!=ApprovalStatus.DELEGATED):raise HTTPException(403,"HR may complete the manager step only after fallback delegation")
        if user.role==Role.ADMIN or user.role==Role.HR or (step and step.assigned_reviewer_id==user.id):
            if not step or step.status not in {ApprovalStatus.PENDING,ApprovalStatus.DELEGATED}:raise HTTPException(409,"Manager step is already decided")
        else:raise HTTPException(403,"You are not assigned this manager approval")
        step.assigned_reviewer_id=user.id;step.decision=body.decision;step.note=body.note;step.decided_at=datetime.now(timezone.utc);step.status=ApprovalStatus.APPROVED if body.decision=="APPROVED" else ApprovalStatus.REJECTED
        r.status=RequestStatus.PENDING_HR if body.decision=="APPROVED" else RequestStatus.REJECTED
    elif body.step=="HR":
        if user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"HR approval required")
        if r.status!=RequestStatus.PENDING_HR:raise HTTPException(409,"HR review starts after manager approval")
        step=db.query(ApprovalStep).filter_by(entity_type="RESIGNATION",entity_id=r.id,step_type="HR").first();step.assigned_reviewer_id=user.id;step.decision=body.decision;step.note=body.note;step.decided_at=datetime.now(timezone.utc);step.status=ApprovalStatus.APPROVED if body.decision=="APPROVED" else ApprovalStatus.REJECTED
        r.status=RequestStatus.APPROVED if body.decision=="APPROVED" else RequestStatus.REJECTED;r.decided_at=datetime.now(timezone.utc)
    else:raise HTTPException(422,"Step must be MANAGER or HR")
    audit(db,user,f"RESIGNATION_{body.step}_{body.decision}","ResignationRequest",r.id,after={"note":body.note});db.commit();return resignation_json(r,db)
