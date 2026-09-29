from typing import List, Optional
from fastapi import FastAPI, Query, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.backend.models import Item, ItemType
from app.backend.db_models import ItemORM, ItemTypeORM
from app.backend.database import get_db
from app.backend.routers.auth import router as auth_router

from fastapi import Form
from fastapi.responses import RedirectResponse
from app.backend.db_models import ItemORM, ItemTypeORM, UserORM, RoleORM
from app.backend.auth import (
    verify_password, hash_password, create_access_token,
    get_current_user_optional, ACCESS_TOKEN_EXPIRE_SECONDS, COOKIE_SECURE,
)

app = FastAPI(title="Магазин мамы", version="0.4.0")

app.mount("/static", StaticFiles(directory="app/backend/static"), name="static")
templates = Jinja2Templates(directory="app/backend/templates")

app.include_router(auth_router)


@app.get("/api/items", response_model=List[Item], tags=["items"])
def get_items(
    item_type: Optional[ItemType] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ItemORM).join(ItemTypeORM, ItemORM.id_item_type == ItemTypeORM.id)
    if item_type is not None:
        query = query.filter(ItemTypeORM.name == item_type.value)
    return query.all()


@app.get("/api/items/{item_id}", response_model=Item, tags=["items"])
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/shop")
def shop_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(ItemORM).all()
    return templates.TemplateResponse(
        request=request,
        name="items.html",
        context={"items": items}
    )

@app.get("/shop/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )

@app.post("/shop/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(UserORM).filter(UserORM.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Неверный email или пароль"},
            status_code=401,
        )

    token = create_access_token(user.id)
    response = RedirectResponse(url="/shop", status_code=303)
    response.set_cookie(
        key="access_token", value=token, httponly=True,
        secure=COOKIE_SECURE, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return response

@app.get("/shop/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="register.html", context={"error": None}
    )


@app.post("/shop/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Пароль должен содержать не менее 8 символов"},
            status_code=400,
        )

    existing = db.query(UserORM).filter(UserORM.email == email).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Этот email уже зарегистрирован"},
            status_code=409,
        )

    default_role = db.query(RoleORM).filter(RoleORM.role_name == "user").first()
    user = UserORM(email=email, password_hash=hash_password(password), id_role=default_role.id)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    response = RedirectResponse(url="/shop", status_code=303)
    response.set_cookie(
        key="access_token", value=token, httponly=True,
        secure=COOKIE_SECURE, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    return response

@app.get("/shop/account")
def account_page(
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    return {"message": f"Привет, {current_user.email}! Личный кабинет — в разработке."}

@app.get("/")
def root():
    return {"message": "API магазина работает. /docs — Swagger, /shop — витрина."}