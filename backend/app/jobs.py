from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func
from .db import SessionLocal
from .models import AttendanceDay, AttendanceStatus, Employee, EmployeeShiftAssignment, LeaveLedger, LeaveType, Shift, Team, TeamSettings

def seed_reference_data():
    db=SessionLocal()
    try:
        if not db.query(Shift).filter_by(code="SHIFT_1").first(): db.add(Shift(code="SHIFT_1",name="Shift 1",starts_at=time(9,30),ends_at=time(18,30),target_work_minutes=480,break_allowance_minutes=60))
        if not db.query(Shift).filter_by(code="SHIFT_2").first(): db.add(Shift(code="SHIFT_2",name="Shift 2",starts_at=time(13,0),ends_at=time(22,0),target_work_minutes=480,break_allowance_minutes=60))
        if not db.query(LeaveType).filter_by(code="CL").first(): db.add(LeaveType(code="CL",name="Casual Leave"))
        if not db.query(LeaveType).filter_by(code="SL").first(): db.add(LeaveType(code="SL",name="Sick Leave"))
        db.commit()
    finally: db.close()

def accrue_monthly_leave(on_date:date|None=None):
    effective=(on_date or date.today()).replace(day=1);db=SessionLocal();created=0
    try:
        types={x.code:x.id for x in db.query(LeaveType).all()}
        for e in db.query(Employee).filter_by(employment_status="ACTIVE").all():
            for code in ("CL","SL"):
                if db.query(LeaveLedger.id).filter_by(employee_id=e.id,leave_type_id=types[code],effective_date=effective,entry_type="ACCRUAL").first():continue
                db.add(LeaveLedger(employee_id=e.id,leave_type_id=types[code],effective_date=effective,amount_days=0.5,entry_type="ACCRUAL",note=f"Monthly {code} accrual"));created+=1
        db.commit();return created
    finally:db.close()

def close_ended_shifts(on_date:date|None=None):
    on_date=on_date or date.today();db=SessionLocal();created=0
    try:
        for e in db.query(Employee).filter_by(employment_status="ACTIVE").all():
            team=db.get(Team,e.team_id) if e.team_id else None
            if not team:continue
            cfg=db.get(TeamSettings,team.id);codes=cfg.enabled_shifts if cfg and cfg.enabled_shifts else ["SHIFT_1"]
            if cfg and cfg.shift_mode.value=="MANAGER_ASSIGNED":
                assignment=db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id==e.id,EmployeeShiftAssignment.valid_from<=on_date).filter((EmployeeShiftAssignment.valid_to.is_(None))|(EmployeeShiftAssignment.valid_to>=on_date)).order_by(EmployeeShiftAssignment.valid_from.desc()).first()
                codes=[db.get(Shift,assignment.shift_id).code] if assignment else [codes[0]]
            shifts=db.query(Shift).filter(Shift.code.in_(codes),Shift.is_active.is_(True)).all()
            if not shifts:continue
            now=datetime.now(ZoneInfo(e.timezone or "Asia/Kolkata"))
            if now.date()!=on_date or now.time()<max(x.ends_at for x in shifts):continue
            if db.query(AttendanceDay.id).filter_by(employee_id=e.id,work_date=on_date).first():continue
            shift=max(shifts,key=lambda x:x.ends_at)
            db.add(AttendanceDay(employee_id=e.id,work_date=on_date,shift_id=shift.id,work_mode="OFFICE",status=AttendanceStatus.ABSENT));created+=1
        db.commit();return created
    finally:db.close()

def close_financial_year(year_end:date|None=None):
    year_end=year_end or date(date.today().year-1,3,31);effective=year_end+timedelta(days=1);db=SessionLocal();count=0
    try:
        for e in db.query(Employee).filter_by(employment_status="ACTIVE").all():
            try:tenure_cutoff=year_end.replace(year=year_end.year-1)
            except ValueError:tenure_cutoff=year_end.replace(year=year_end.year-1,day=28)
            qualified=e.join_date<=tenure_cutoff
            for lt in db.query(LeaveType).all():
                balance=float(db.query(func.coalesce(func.sum(LeaveLedger.amount_days),0)).filter(LeaveLedger.employee_id==e.id,LeaveLedger.leave_type_id==lt.id,LeaveLedger.effective_date<=year_end).scalar() or 0)
                action="FY_CARRY_FORWARD" if qualified else "FY_RESET"
                if db.query(LeaveLedger.id).filter_by(employee_id=e.id,leave_type_id=lt.id,effective_date=effective,entry_type=action).first():continue
                if balance:db.add(LeaveLedger(employee_id=e.id,leave_type_id=lt.id,effective_date=effective,amount_days=-balance,entry_type="FY_CLOSE_REVERSAL",note=f"Financial year close {year_end.isoformat()}"))
                if qualified and balance:db.add(LeaveLedger(employee_id=e.id,leave_type_id=lt.id,effective_date=effective,amount_days=balance,entry_type="FY_CARRY_FORWARD",note="Carry forward after one year of service"))
                if not qualified:db.add(LeaveLedger(employee_id=e.id,leave_type_id=lt.id,effective_date=effective,amount_days=0,entry_type="FY_RESET",note="Reset because one year of service was not completed"))
                count+=1
        db.commit();return count
    finally:db.close()

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("job",choices=["seed","accrual","close-shifts","close-financial-year"]);a=p.parse_args()
    if a.job=="seed":seed_reference_data();print("Reference data ready")
    elif a.job=="accrual":print(f"Created {accrue_monthly_leave()} accrual rows")
    elif a.job=="close-shifts":print(f"Marked {close_ended_shifts()} employees absent")
    else:print(f"Processed {close_financial_year()} leave entries")
