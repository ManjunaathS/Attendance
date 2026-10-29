from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import Event, EventMedia, NewsPost, Policy, PublishStatus, Role, User
from .auth import current_user, roles
from ..services.audit import audit

router=APIRouter(prefix="/api/v1",tags=["policies","news","events"])
class ContentBody(BaseModel):
    title:str=Field(min_length=2,max_length=180)
    body:str=Field(min_length=1,max_length=50000)
    status:PublishStatus=PublishStatus.DRAFT
class EventBody(BaseModel):
    title:str=Field(min_length=2,max_length=180)
    description:str|None=None
    starts_at:datetime
    time_unspecified:bool=False
    ends_at:datetime|None=None
    location:str|None=None
    status:PublishStatus=PublishStatus.DRAFT

def can_edit_policy(u):return u.role in {Role.HR,Role.ADMIN}
def can_edit_news(u):return u.role in {Role.MANAGER,Role.HR,Role.ADMIN}
def media_dir():
    p=Path(settings.media_dir).resolve();p.mkdir(parents=True,exist_ok=True);return p
@router.get("/policies")
def list_policies(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Policy)
    if user.role in {Role.EMPLOYEE,Role.MANAGER}:q=q.filter(Policy.status==PublishStatus.PUBLISHED)
    return [{"id":str(p.id),"title":p.title,"body":p.body,"status":p.status.value,"version":p.version,"updated_at":p.updated_at.isoformat()} for p in q.order_by(Policy.updated_at.desc()).all()]
@router.post("/policies",status_code=201)
def create_policy(body:ContentBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    p=Policy(title=body.title,body=body.body,status=body.status,created_by=user.id,updated_by=user.id,published_at=datetime.now(timezone.utc) if body.status==PublishStatus.PUBLISHED else None)
    db.add(p);db.flush();audit(db,user,"POLICY_CREATED","Policy",p.id,after={"title":p.title,"status":p.status.value});db.commit();db.refresh(p);return {"id":str(p.id),"title":p.title,"status":p.status.value}
@router.patch("/policies/{item_id}")
def update_policy(item_id:UUID,body:ContentBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    p=db.get(Policy,item_id)
    if not p:raise HTTPException(404,"Policy not found")
    before={"title":p.title,"body":p.body,"status":p.status.value};p.title=body.title;p.body=body.body;p.version+=1;p.status=body.status;p.updated_by=user.id
    if p.status==PublishStatus.PUBLISHED and not p.published_at:p.published_at=datetime.now(timezone.utc)
    audit(db,user,"POLICY_UPDATED","Policy",p.id,before=before,after={"title":p.title,"version":p.version,"status":p.status.value});db.commit();return {"id":str(p.id),"title":p.title,"status":p.status.value,"version":p.version}
@router.get("/news")
def list_news(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(NewsPost)
    if user.role in {Role.EMPLOYEE}:q=q.filter(NewsPost.status==PublishStatus.PUBLISHED)
    return [{"id":str(n.id),"title":n.title,"body":n.body,"status":n.status.value,"published_at":n.published_at.isoformat() if n.published_at else None} for n in q.order_by(NewsPost.published_at.desc().nullslast()).all()]
@router.post("/news",status_code=201)
def create_news(body:ContentBody,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","HR","ADMIN"))):
    n=NewsPost(title=body.title,body=body.body,status=body.status,author_id=user.id,published_at=datetime.now(timezone.utc) if body.status==PublishStatus.PUBLISHED else None)
    db.add(n);db.flush();audit(db,user,"NEWS_CREATED","NewsPost",n.id,after={"title":n.title,"status":n.status.value});db.commit();db.refresh(n);return {"id":str(n.id),"title":n.title,"status":n.status.value}
@router.patch("/news/{item_id}")
def update_news(item_id:UUID,body:ContentBody,db:Session=Depends(get_db),user:User=Depends(roles("MANAGER","HR","ADMIN"))):
    n=db.get(NewsPost,item_id)
    if not n:raise HTTPException(404,"News post not found")
    n.title=body.title;n.body=body.body;n.status=body.status
    if n.status==PublishStatus.PUBLISHED and not n.published_at:n.published_at=datetime.now(timezone.utc)
    audit(db,user,"NEWS_UPDATED","NewsPost",n.id,after={"title":n.title,"status":n.status.value});db.commit();return {"id":str(n.id),"title":n.title,"status":n.status.value}
@router.get("/events")
def list_events(db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=db.query(Event)
    if user.role in {Role.EMPLOYEE,Role.MANAGER}:q=q.filter(Event.status==PublishStatus.PUBLISHED)
    return [{"id":str(e.id),"title":e.title,"description":e.description,"starts_at":e.starts_at.isoformat(),"time_unspecified":e.time_unspecified,"ends_at":e.ends_at.isoformat() if e.ends_at else None,"location":e.location,"status":e.status.value,"photos":[{"id":str(m.id),"caption":m.caption,"url":f"/api/v1/events/{e.id}/media/{m.id}"} for m in e.media]} for e in q.order_by(Event.starts_at).all()]
@router.post("/events",status_code=201)
def create_event(body:EventBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    e=Event(title=body.title,description=body.description,starts_at=body.starts_at,time_unspecified=body.time_unspecified,ends_at=body.ends_at,location=body.location,status=body.status,author_id=user.id,published_at=datetime.now(timezone.utc) if body.status==PublishStatus.PUBLISHED else None)
    db.add(e);db.flush();audit(db,user,"EVENT_CREATED","Event",e.id,after={"title":e.title});db.commit();return {"id":str(e.id),"title":e.title,"status":e.status.value}
@router.patch("/events/{event_id}")
def update_event(event_id:UUID,body:EventBody,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    e=db.get(Event,event_id)
    if not e:raise HTTPException(404,"Event not found")
    e.title=body.title;e.description=body.description;e.starts_at=body.starts_at;e.time_unspecified=body.time_unspecified;e.ends_at=body.ends_at;e.location=body.location;e.status=body.status
    if e.status==PublishStatus.PUBLISHED and not e.published_at:e.published_at=datetime.now(timezone.utc)
    audit(db,user,"EVENT_UPDATED","Event",e.id,after={"title":e.title});db.commit();return {"id":str(e.id),"title":e.title,"status":e.status.value}
@router.post("/events/{event_id}/media",status_code=201)
async def upload_event_photo(event_id:UUID,file:UploadFile=File(...),caption:str|None=None,db:Session=Depends(get_db),user:User=Depends(roles("HR","ADMIN"))):
    event=db.get(Event,event_id)
    if not event:raise HTTPException(404,"Event not found")
    data=await file.read(settings.max_upload_mb*1024*1024+1)
    if len(data)>settings.max_upload_mb*1024*1024:raise HTTPException(413,"Image exceeds upload size limit")
    try:
        image=Image.open(__import__('io').BytesIO(data));image.verify();content_type=Image.MIME.get(image.format)
    except (UnidentifiedImageError, OSError):raise HTTPException(415,"Upload must be a valid image")
    if content_type not in {"image/jpeg","image/png","image/webp"}:raise HTTPException(415,"Use JPEG, PNG, or WebP images")
    key=f"{event_id}/{uuid4().hex}.{content_type.split('/')[-1]}";target=media_dir()/key;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    media=EventMedia(event_id=event.id,object_key=key,content_type=content_type,size_bytes=len(data),uploaded_by=user.id,caption=caption)
    db.add(media);audit(db,user,"EVENT_PHOTO_UPLOADED","EventMedia",media.id,after={"event_id":str(event.id),"size_bytes":len(data)});db.commit();db.refresh(media)
    return {"id":str(media.id),"url":f"/api/v1/events/{event.id}/media/{media.id}","caption":media.caption}
@router.get("/events/{event_id}/media/{media_id}")
def get_event_photo(event_id:UUID,media_id:UUID,db:Session=Depends(get_db),user:User=Depends(current_user)):
    e=db.get(Event,event_id);m=db.query(EventMedia).filter_by(id=media_id,event_id=event_id).first()
    if not e or not m:raise HTTPException(404,"Photo not found")
    if e.status!=PublishStatus.PUBLISHED and user.role not in {Role.HR,Role.ADMIN}:raise HTTPException(404,"Photo not found")
    path=(media_dir()/m.object_key).resolve()
    if not path.is_relative_to(media_dir()):raise HTTPException(404,"Photo not found")
    return FileResponse(path,media_type=m.content_type,filename=path.name)
