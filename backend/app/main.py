from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api import activities, auth, attendance, content, employees, organization, requests, tasks
from .jobs import accrue_monthly_leave, close_ended_shifts, close_financial_year

scheduler=BackgroundScheduler(timezone=ZoneInfo(settings.company_timezone))
@asynccontextmanager
async def lifespan(app:FastAPI):
    scheduler.add_job(close_ended_shifts,"interval",minutes=1,id="attendance-absence",replace_existing=True,max_instances=1)
    scheduler.add_job(accrue_monthly_leave,CronTrigger(day=1,hour=0,minute=15),id="monthly-leave-accrual",replace_existing=True,max_instances=1)
    scheduler.add_job(close_financial_year,CronTrigger(month=4,day=1,hour=0,minute=30),id="financial-year-close",replace_existing=True,max_instances=1)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app=FastAPI(title="Attendrix API",version="1.0.0",description="Attendance and people operations",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE"],allow_headers=["Content-Type","X-Request-ID"])
for router in (auth.router,attendance.router,requests.router,tasks.router,activities.router,content.router,organization.router,employees.router):app.include_router(router)
@app.get("/api/v1/health",tags=["health"])
def health():return {"status":"ok","service":"attendrix-api"}
