from typing import Literal
from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Role, AuditLog
from ..schemas import UserCreate, UserOut, TokenOut
from ..security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginForm:
    def __init__(
        self,
        username: str = Form(),
        password: str = Form(),
        account_type: Literal["employee", "author"] = Form(default="author"),
    ):
        self.username = username
        self.password = password
        self.account_type = account_type

@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    # Public registration deliberately grants no privileged role. In production, disable public
    # registration or require an administrator invitation if this is an internal company CRM.
    email = str(payload.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(full_name=payload.full_name, email=email, password_hash=hash_password(payload.password))
    employee_role = db.query(Role).filter(Role.name == "Employee / Intern").first()
    if employee_role:
        user.roles.append(employee_role)
    db.add(user); db.flush()
    db.add(AuditLog(user_id=user.id, action="user.registered", entity_type="user", entity_id=str(user.id)))
    db.commit(); db.refresh(user)
    return UserOut(id=user.id, full_name=user.full_name, email=user.email, is_active=user.is_active, roles=[r.name for r in user.roles])

@router.post("/login", response_model=TokenOut)
def login(form: LoginForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username.lower()).first()
    if not user or not verify_password(form.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    roles = {role.name for role in user.roles}
    is_author = bool(roles.intersection({"Super Admin", "Management"}))
    if form.account_type == "employee" and ("Employee / Intern" not in roles or is_author):
        raise HTTPException(status_code=403, detail="Choose Author for this account")
    if form.account_type == "author" and not is_author:
        raise HTTPException(status_code=403, detail="This account is not an Author account")
    return TokenOut(access_token=create_access_token(user.id))

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, full_name=user.full_name, email=user.email, is_active=user.is_active, roles=[r.name for r in user.roles])
