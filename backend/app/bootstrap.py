from datetime import datetime, timezone
import os
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from .db import SessionLocal
from .jobs import seed_reference_data
from .models import Role, User


def bootstrap():
    seed_reference_data()
    login=os.getenv("ATTEND_ADMIN_LOGIN")
    password=os.getenv("ATTEND_ADMIN_PASSWORD")
    if not login or not password:
        print("Admin bootstrap skipped; set ATTEND_ADMIN_LOGIN and ATTEND_ADMIN_PASSWORD to create the first Admin account.")
        return
    if len(password)<14:raise SystemExit("ATTEND_ADMIN_PASSWORD must be at least 14 characters")
    db:Session=SessionLocal()
    try:
        user=db.query(User).filter_by(login_id=login).first()
        if not user:
            db.add(User(login_id=login,password_hash=PasswordHash.recommended().hash(password),role=Role.ADMIN,is_active=True));db.commit();print(f"Created Admin login {login}")
        else:print(f"Admin login {login} already exists")
    finally:db.close()
if __name__=="__main__":bootstrap()
