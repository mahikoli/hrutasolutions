from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db, settings
from .models import User

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)

def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.secret_key, algorithm=ALGORITHM)

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauth = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise unauth
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise unauth
    roles = {role.name for role in user.roles}
    employee_only = "Employee / Intern" in roles and not roles.intersection({"Super Admin", "Management"})
    if employee_only:
        path = request.url.path
        method = request.method.upper()
        allowed = (
            (method == "GET" and path in {"/api/v1/auth/me", "/api/v1/tasks"})
            or (method == "PATCH" and path.startswith("/api/v1/tasks/") and path.removeprefix("/api/v1/tasks/").isdigit())
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Employee accounts can only access assigned tasks")
    return user

def require_roles(*allowed: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        names = {r.name for r in user.roles}
        if not names.intersection(allowed):
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return checker
