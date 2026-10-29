from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import Employee, User
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
class LoginBody(BaseModel):
    login_id: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)
class UserView(BaseModel):
    id: str
    role: str
    employee_id: str | None
    display_name: str

@router.post("/login", response_model=UserView)
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login_id == body.login_id, User.is_active.is_(True)).first()
    if not user or not hasher.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Login ID or password is incorrect")
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm="HS256")
    response.set_cookie("attend_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.jwt_expire_minutes * 60, path="/")
    user.last_login_at = now
    db.commit()
    return UserView(id=str(user.id), role=user.role.value, employee_id=str(user.employee_id) if user.employee_id else None, display_name=user.employee.full_name if user.employee else user.login_id)

def establish_session(user: User, response: Response, db: Session) -> UserView:
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm="HS256")
    response.set_cookie("attend_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.jwt_expire_minutes * 60, path="/")
    user.last_login_at = now
    db.commit()
    return UserView(id=str(user.id), role=user.role.value, employee_id=str(user.employee_id) if user.employee_id else None, display_name=user.employee.full_name if user.employee else user.login_id)

@router.post("/neon/link", response_model=UserView)
def link_neon_account(response: Response, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    if not settings.neon_auth_base_url or not settings.neon_auth_jwks_url:
        raise HTTPException(status_code=503, detail="Neon Auth is not configured")
    token = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="A Neon Auth token is required")
    auth_origin = urlsplit(settings.neon_auth_base_url)
    issuer = f"{auth_origin.scheme}://{auth_origin.netloc}"
    try:
        signing_key = jwt.PyJWKClient(settings.neon_auth_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, signing_key, algorithms=["EdDSA"], issuer=issuer, audience=issuer)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Neon Auth token is invalid or expired")
    email = claims.get("email")
    if claims.get("emailVerified") is not True or not isinstance(email, str):
        raise HTTPException(status_code=403, detail="Verify your work email before linking your account")
    user = db.query(User).join(Employee, User.employee_id == Employee.id).filter(
        User.is_active.is_(True),
        Employee.employment_status == "ACTIVE",
        func.lower(Employee.work_email) == email.casefold(),
    ).first()
    if not user:
        raise HTTPException(status_code=403, detail="No active employee account is linked to this work email")
    return establish_session(user, response, db)

@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("attend_session", path="/")

@router.get("/me", response_model=UserView)
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return UserView(id=str(user.id), role=user.role.value, employee_id=str(user.employee_id) if user.employee_id else None, display_name=user.employee.full_name if user.employee else user.login_id)

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("attend_session")
    if not token: raise HTTPException(status_code=401, detail="Please sign in")
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = UUID(data.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again")
    user = db.get(User, user_id)
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="Account is inactive")
    return user

@router.get("/realtime-identity")
def realtime_identity(user: User = Depends(current_user)):
    employee = user.employee
    return {
        "role": user.role.value,
        "employee_id": str(user.employee_id) if user.employee_id else None,
        "team_id": str(employee.team_id) if employee and employee.team_id else None,
    }

def roles(*allowed: str):
    def dependency(user: User = Depends(current_user)):
        if user.role.value not in allowed: raise HTTPException(status_code=403, detail="You do not have access to this action")
        return user
    return dependency

require_user = Depends(current_user)
