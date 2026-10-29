from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Employee, Role, Task, TaskStatus, TaskStatusHistory, User
from .auth import current_user, roles
from ..services.audit import audit

router=APIRouter(prefix="/api/v1/tasks",tags=["tasks"])
class TaskCreate(BaseModel):
    title:str=Field(min_length=1,max_length=180)
    assignee_id:UUID
    description:str|None=None
    due_date:date|None=None
    priority:str="NORMAL"
class TaskUpdate(BaseModel):
    status:TaskStatus|None=None
    pending_reason:str|None=None
    title:str|None=None
    description:str|None=None
    due_date:date|None=None
    priority:str|None=None

def task_json(t:Task,db:Session):
    assigned_to=db.get(Employee,t.assigned_to);assigned_by=db.get(Employee,t.assigned_by)
    return {"id":str(t.id),"team_id":str(t.team_id),"title":t.title,"description":t.description,"assignee_id":str(t.assigned_to),"assignee":assigned_to.full_name if assigned_to else "","assigner":assigned_by.full_name if assigned_by else "","due_date":t.due_at.isoformat() if t.due_at else None,"priority":t.priority,"status":t.status.value,"pending_reason":t.pending_reason}
@router.get("")
def list_tasks(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Task)
    if user.role==Role.EMPLOYEE:q=q.filter(Task.assigned_to==user.employee_id)
    elif user.role==Role.MANAGER:
        if not user.employee or not user.employee.team_id:return []
        q=q.filter(Task.team_id==user.employee.team_id)
    elif user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    return [task_json(t,db) for t in q.order_by(Task.due_at.asc().nullslast(),Task.created_at.desc()).limit(500).all()]
@router.post("",status_code=201)
def create_task(body:TaskCreate,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","ADMIN"))):
    assignee=db.get(Employee,body.assignee_id)
    if not assignee or assignee.employment_status!="ACTIVE":raise HTTPException(404,"Active assignee not found")
    if user.role==Role.MANAGER and (not user.employee or assignee.team_id!=user.employee.team_id):raise HTTPException(403,"You can assign only within your team")
    if not assignee.team_id:raise HTTPException(422,"Assignee must belong to a team")
    task=Task(team_id=assignee.team_id,title=body.title,description=body.description,assigned_by=user.employee_id or assignee.id,assigned_to=assignee.id,due_at=body.due_date,priority=body.priority.upper())
    db.add(task);db.flush();db.add(TaskStatusHistory(task_id=task.id,new_status=TaskStatus.NOT_STARTED.value,actor_id=user.id));audit(db,user,"TASK_ASSIGNED","Task",task.id,after={"assigned_to":str(assignee.id),"title":body.title});db.commit();db.refresh(task)
    return task_json(task,db)
@router.patch("/{task_id}")
def update_task(task_id:UUID,body:TaskUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    task=db.get(Task,task_id)
    if not task:raise HTTPException(404,"Task not found")
    if user.role==Role.MANAGER and (not user.employee or task.team_id!=user.employee.team_id):raise HTTPException(403,"Task is outside your team")
    if user.role==Role.EMPLOYEE and task.assigned_to!=user.employee_id:raise HTTPException(403,"You can update only your own task")
    if user.role not in {Role.EMPLOYEE,Role.MANAGER,Role.ADMIN}:raise HTTPException(403,"Not authorized")
    before=task.status.value
    if body.status is not None:
        if body.status==TaskStatus.PENDING and not (body.pending_reason or task.pending_reason):raise HTTPException(422,"Add a reason when marking a task Pending")
        task.status=body.status;task.pending_reason=body.pending_reason
        db.add(TaskStatusHistory(task_id=task.id,old_status=before,new_status=body.status.value,reason=body.pending_reason,actor_id=user.id))
    if user.role in {Role.MANAGER,Role.ADMIN}:
        for k in ("title","description","due_date","priority"):
            v=getattr(body,k)
            if v is not None:setattr(task,{"due_date":"due_at"}.get(k,k),v.upper() if k=="priority" else v)
    audit(db,user,"TASK_UPDATED","Task",task.id,before={"status":before},after={"status":task.status.value});db.commit();db.refresh(task);return task_json(task,db)
