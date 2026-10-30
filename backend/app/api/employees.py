from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Employee, Role, Team, TeamSettings, User
from .auth import current_user, roles
from ..services.audit import audit
from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID

router=APIRouter(prefix="/api/v1",tags=["employees","teams"])
class EmployeeCreate(BaseModel):
    employee_number:str=Field(min_length=1,max_length=40)
    full_name:str=Field(min_length=1,max_length=180)
    work_email:str
    login_id:str=Field(min_length=1,max_length=120)
    temporary_password:str=Field(min_length=12,max_length=128)
    role:Role=Role.EMPLOYEE
    job_title:str="Employee"
    team_id:UUID|None=None
    reports_to_employee_id:UUID|None=None
    join_date:date
    timezone:str="Asia/Kolkata"
class TeamCreate(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    manager_employee_id:UUID|None=None
    shift_mode:str="EMPLOYEE_SELECT"
    enabled_shifts:list[str]=["SHIFT_1"]
    wfh_advance_notice_days:int=Field(default=1,ge=0,le=90)
@router.get("/employees")
def list_employees(db:Session=Depends(get_db), user:User=Depends(current_user)):
    q=db.query(Employee)
    if user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        q=q.filter(Employee.team_id==user.employee.team_id)
    if user.role==Role.EMPLOYEE:q=q.filter(Employee.id==user.employee_id)
    return [{"id":str(e.id),"employee_number":e.employee_number,"full_name":e.full_name,"email":e.work_email,"phone":e.phone,"job_title":e.job_title,"team_id":str(e.team_id) if e.team_id else None,"manager_id":str(e.reports_to_employee_id) if e.reports_to_employee_id else None,"join_date":e.join_date.isoformat(),"status":e.employment_status,"role":e.user.role.value if e.user else "EMPLOYEE",**({"login_id":e.user.login_id if e.user else None} if user.role in {Role.HR,Role.ADMIN} else {})} for e in q.order_by(Employee.full_name).all()]
@router.post("/employees",status_code=201)
def create_employee(body:EmployeeCreate,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR"))):
    from .auth import hasher
    if body.role==Role.ADMIN and user.role!=Role.ADMIN: raise HTTPException(403,"Only Admin can create an Admin account")
    team=db.get(Team,body.team_id) if body.team_id else None
    if body.team_id and not team:raise HTTPException(422,"Unknown team")
    if body.role==Role.MANAGER and team and team.manager_employee_id:
        raise HTTPException(409,"This team already has a Manager. Choose another team or assign the new Manager later.")
    e=Employee(employee_number=body.employee_number,full_name=body.full_name,work_email=body.work_email,job_title=body.job_title,team_id=body.team_id,reports_to_employee_id=body.reports_to_employee_id,join_date=body.join_date,timezone=body.timezone)
    db.add(e);db.flush()
    u=User(login_id=body.login_id,password_hash=hasher.hash(body.temporary_password),role=body.role,employee_id=e.id,is_active=True)
    db.add(u)
    if body.role==Role.MANAGER and team:team.manager_employee_id=e.id
    db.commit();db.refresh(e)
    return {"id":str(e.id),"user_id":str(u.id),"full_name":e.full_name,"role":u.role.value}
@router.patch("/employees/{employee_id}")
def update_employee(employee_id:UUID,body:dict,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR"))):
    from .auth import hasher
    e=db.get(Employee,employee_id)
    if not e:raise HTTPException(404,"Employee not found")
    if "employee_number" in body:
        number=str(body["employee_number"]).strip()
        if not number:raise HTTPException(422,"Employee ID cannot be empty")
        duplicate=db.query(Employee).filter(Employee.employee_number==number,Employee.id!=e.id).first()
        if duplicate:raise HTTPException(409,"Employee ID is already in use")
        e.employee_number=number
    if "work_email" in body:
        email=str(body["work_email"]).strip().lower()
        duplicate=db.query(Employee).filter(Employee.work_email==email,Employee.id!=e.id).first()
        if duplicate:raise HTTPException(409,"Work email is already in use")
        e.work_email=email
    if "login_id" in body:
        if not e.user:raise HTTPException(422,"Employee has no linked login account")
        login_id=str(body["login_id"]).strip()
        if not login_id:raise HTTPException(422,"Login ID cannot be empty")
        duplicate=db.query(User).filter(User.login_id==login_id,User.id!=e.user.id).first()
        if duplicate:raise HTTPException(409,"Login ID is already in use")
        old_login=e.user.login_id;e.user.login_id=login_id
        audit(db,user,"EMPLOYEE_LOGIN_CHANGED","Employee",e.id,before={"login_id":old_login},after={"login_id":login_id})
    if body.get("password"):
        if not e.user:raise HTTPException(422,"Employee has no linked login account")
        if len(body["password"])<12:raise HTTPException(422,"Password must be at least 12 characters")
        e.user.password_hash=hasher.hash(body["password"])
        audit(db,user,"EMPLOYEE_PASSWORD_RESET","Employee",e.id)
    if "join_date" in body:
        try:e.join_date=date.fromisoformat(body["join_date"])
        except (TypeError,ValueError):raise HTTPException(422,"Invalid join date")
    if "team_id" in body:
        try:new_team_id=UUID(body["team_id"]) if body["team_id"] else None
        except (TypeError,ValueError):raise HTTPException(422,"Invalid team ID")
        new_team=db.get(Team,new_team_id) if new_team_id else None
        if new_team_id and not new_team:raise HTTPException(422,"Unknown team")
        if e.team_id!=new_team_id:
            old_team=db.get(Team,e.team_id) if e.team_id else None
            if old_team and old_team.manager_employee_id==e.id:old_team.manager_employee_id=None
            if new_team and new_team.manager_employee_id not in {None,e.id} and e.user and e.user.role==Role.MANAGER:
                raise HTTPException(409,"The selected team already has a manager")
            e.team_id=new_team_id
            if new_team and e.user and e.user.role==Role.MANAGER:new_team.manager_employee_id=e.id
    if "role" in body:
        if user.role!=Role.ADMIN:raise HTTPException(403,"Only Admin can change account roles")
        if not e.user:raise HTTPException(422,"Employee has no linked login account")
        try:new_role=Role(body["role"])
        except ValueError:raise HTTPException(422,"Role must be EMPLOYEE, MANAGER, or HR")
        if new_role==Role.ADMIN:raise HTTPException(422,"Admin role cannot be assigned through employee role editing")
        if e.user.role==Role.MANAGER and new_role!=Role.MANAGER and db.query(Team).filter_by(manager_employee_id=e.id).first():
            raise HTTPException(409,"Assign another team manager before changing this Manager account's role")
        if new_role==Role.MANAGER and e.team_id:
            team=db.get(Team,e.team_id)
            if team and team.manager_employee_id not in {None,e.id}:
                raise HTTPException(409,"This team already has a Manager. Assign the employee to another team before changing the role.")
            if team:team.manager_employee_id=e.id
        old_role=e.user.role.value;e.user.role=new_role
        audit(db,user,"EMPLOYEE_ROLE_CHANGED","Employee",e.id,before={"role":old_role},after={"role":new_role.value})
    for k in ("full_name","phone","job_title","reports_to_employee_id","employment_status","timezone"):
        if k in body:setattr(e,k,body[k])
    audit(db,user,"EMPLOYEE_PROFILE_UPDATED","Employee",e.id,after={k:v for k,v in body.items() if k!="password"})
    db.commit();return {"id":str(e.id),"full_name":e.full_name,"employee_number":e.employee_number,"login_id":e.user.login_id if e.user else None,"role":e.user.role.value if e.user else None}
@router.get("/teams")
def list_teams(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Team)
    if user.role==Role.MANAGER and user.employee and user.employee.team_id:q=q.filter(Team.id==user.employee.team_id)
    if user.role==Role.EMPLOYEE and user.employee and user.employee.team_id:q=q.filter(Team.id==user.employee.team_id)
    return [{"id":str(t.id),"name":t.name,"manager_employee_id":str(t.manager_employee_id) if t.manager_employee_id else None,"employee_count":len(t.employees),"shift_mode":t.settings.shift_mode.value if t.settings else "EMPLOYEE_SELECT","enabled_shifts":t.settings.enabled_shifts if t.settings else ["SHIFT_1"],"wfh_advance_notice_days":t.settings.wfh_advance_notice_days if t.settings else 1} for t in q.order_by(Team.name).all()]
@router.post("/teams",status_code=201)
def create_team(body:TeamCreate,db:Session=Depends(get_db),user:User=Depends(roles("ADMIN","HR"))):
    if not body.enabled_shifts:raise HTTPException(422,"Enable at least one shift")
    manager=db.get(Employee,body.manager_employee_id) if body.manager_employee_id else None
    if body.manager_employee_id and (not manager or not manager.user or manager.user.role!=Role.MANAGER):raise HTTPException(422,"Team manager must have a Manager account")
    if manager and manager.team_id:raise HTTPException(409,"This Manager is already assigned to another team")
    t=Team(name=body.name,manager_employee_id=body.manager_employee_id);db.add(t);db.flush()
    if manager:manager.team_id=t.id
    db.add(TeamSettings(team_id=t.id,shift_mode=body.shift_mode,enabled_shifts=body.enabled_shifts,wfh_advance_notice_days=body.wfh_advance_notice_days));audit(db,user,"TEAM_CREATED","Team",t.id,after={"name":t.name,"manager_employee_id":str(t.manager_employee_id) if t.manager_employee_id else None});db.commit();db.refresh(t)
    return {"id":str(t.id),"name":t.name}
