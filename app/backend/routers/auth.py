from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.backend.database import get_db
from app.backend.db_models import UserORM
from app.backend.models import UserCreate, UserOut, LoginRequest, TokenResponse
from app.backend.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_SECONDS, COOKIE_SECURE,
)
from app.backend.services.user_service import generate_unique_login

router = APIRouter(prefix="/api")


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(UserORM).filter(UserORM.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = UserORM(
        email=payload.email,
        login=generate_unique_login(db, payload.email),
        password_hash=hash_password(payload.password),
        id_role=default_role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(UserORM).filter(UserORM.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user.id)
    response.set_cookie(
        key="access_token", value=token, httponly=True,
        secure=COOKIE_SECURE, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return TokenResponse(access_token=token, expires_in=ACCESS_TOKEN_EXPIRE_SECONDS)


@router.post("/auth/logout", tags=["auth"])
def logout(response: Response, current_user: UserORM = Depends(get_current_user)):
    response.delete_cookie("access_token")
    return {"detail": "Logged out"}


@router.get("/users/me", response_model=UserOut, tags=["users"])
def read_current_user(current_user: UserORM = Depends(get_current_user)):
    return current_user