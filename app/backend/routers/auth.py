from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.backend.auth import (
    ACCESS_TOKEN_EXPIRE_SECONDS, authenticate, create_access_token,
    get_current_user, hash_password, set_auth_cookie,
)
from app.backend.database import get_db
from app.backend.db_models import RoleORM, UserORM
from app.backend.models import LoginRequest, TokenResponse, UserCreate, UserOut
from app.backend.security import (
    client_ip, login_limiter_email, login_limiter_ip, register_limiter, validate_new_password,
)
from app.backend.services.user_service import generate_unique_login

router = APIRouter(prefix="/api")


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if register_limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")
    register_limiter.hit(ip)

    try:
        validate_new_password(payload.password)
    except ValueError:
        raise HTTPException(status_code=400, detail="Password must be 8 to 72 bytes long")

    email = payload.email.lower()
    if db.query(UserORM.id).filter(func.lower(UserORM.email) == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    default_role = db.query(RoleORM).filter(RoleORM.role_name == "user").first()
    user = UserORM(
        email=email,
        login=generate_unique_login(db, email),
        password_hash=hash_password(payload.password),
        id_role=default_role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    ip = client_ip(request)
    if login_limiter_ip.is_blocked(ip) or login_limiter_email.is_blocked(email):
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")

    user = db.query(UserORM).filter(func.lower(UserORM.email) == email).first()
    if not authenticate(user, payload.password):
        login_limiter_ip.hit(ip)
        login_limiter_email.hit(email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    login_limiter_email.reset(email)
    set_auth_cookie(response, request, create_access_token(user.id))
    return TokenResponse(access_token=create_access_token(user.id), expires_in=ACCESS_TOKEN_EXPIRE_SECONDS)


@router.post("/auth/logout", tags=["auth"])
def logout(response: Response, current_user: UserORM = Depends(get_current_user)):
    response.delete_cookie("access_token")
    return {"detail": "Logged out"}


@router.get("/users/me", response_model=UserOut, tags=["users"])
def read_current_user(current_user: UserORM = Depends(get_current_user)):
    return current_user