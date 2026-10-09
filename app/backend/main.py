from typing import List, Optional
from fastapi import FastAPI, Query, Depends, Request, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.backend.models import Item, ItemType
from app.backend.database import get_db
from app.backend.db_models import ItemORM, ItemTypeORM, CategoryORM, UserORM, RoleORM
from app.backend.services.items_service import query_items
from app.backend.services.cart_service import (
    get_or_create_cart, build_cart_response, add_item_to_cart,
    update_item_quantity, remove_item_from_cart,
)
from app.backend.auth import (
    verify_password, hash_password, create_access_token,
    get_current_user_optional, ACCESS_TOKEN_EXPIRE_SECONDS, COOKIE_SECURE,
)
from app.backend.routers.auth import router as auth_router
from app.backend.routers.cart import router as cart_router
from app.backend.services.order_service import create_order_from_cart, get_user_order

app = FastAPI(title="Магазин мамы", version="0.5.0")

app.mount("/static", StaticFiles(directory="app/backend/static"), name="static")
templates = Jinja2Templates(directory="app/backend/templates")

app.include_router(auth_router)
app.include_router(cart_router)


# --- Items API ---

@app.get("/api/items", response_model=List[Item], tags=["items"])
def get_items(
    item_type: Optional[ItemType] = Query(None),
    category: Optional[List[str]] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return query_items(
        db,
        item_type=item_type.value if item_type else None,
        categories=category,
        min_price=min_price,
        max_price=max_price,
        search=search,
    )


@app.get("/api/items/{item_id}", response_model=Item, tags=["items"])
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# --- Web: витрина, каталог, карточка товара ---

@app.get("/shop")
def shop_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(ItemORM).all()
    return templates.TemplateResponse(
        request=request, name="items.html", context={"items": items}
    )


@app.get("/shop/catalog")
def catalog_page(
    request: Request,
    item_type: Optional[str] = Query(None),
    category: Optional[List[str]] = Query(None),
    max_price: float = Query(5000),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    all_categories = db.query(CategoryORM).all()
    items = query_items(db, item_type=item_type, categories=category, max_price=max_price, search=search)
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "items": items,
            "all_categories": all_categories,
            "selected_categories": category or [],
            "selected_type": item_type or "",
            "max_price": max_price,
            "search": search or "",
        },
    )


@app.get("/shop/items/{item_id}")
def item_detail_page(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        return templates.TemplateResponse(
            request=request, name="404.html",
            context={"message": "Товар не найден"}, status_code=404,
        )
    return templates.TemplateResponse(
        request=request, name="item_detail.html", context={"item": item}
    )


# --- Web: авторизация ---

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


# --- Web: корзина ---

@app.get("/shop/cart")
def cart_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    cart = get_or_create_cart(db, current_user.id)
    cart_data = build_cart_response(db, cart)
    return templates.TemplateResponse(request=request, name="cart.html", context={"cart": cart_data})


@app.post("/shop/cart/add")
def cart_add_web(
    item_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    add_item_to_cart(db, current_user.id, item_id, quantity)
    return RedirectResponse(url="/shop/cart", status_code=303)


@app.post("/shop/cart/update/{item_id}")
def cart_update_web(
    item_id: int,
    action: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    cart = get_or_create_cart(db, current_user.id)
    current_item = next((ci for ci in cart.items_rel if ci.item_id == item_id), None)
    if current_item is not None:
        new_qty = current_item.quantity + 1 if action == "increase" else max(1, current_item.quantity - 1)
        try:
            update_item_quantity(db, current_user.id, item_id, new_qty)
        except HTTPException:
            pass
    return RedirectResponse(url="/shop/cart", status_code=303)


@app.post("/shop/cart/remove/{item_id}")
def cart_remove_web(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    remove_item_from_cart(db, current_user.id, item_id)
    return RedirectResponse(url="/shop/cart", status_code=303)

@app.get("/shop/checkout")
def checkout_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    cart = get_or_create_cart(db, current_user.id)
    cart_data = build_cart_response(db, cart)
    if not cart_data.items:
        return RedirectResponse(url="/shop/cart", status_code=303)
    return templates.TemplateResponse(
        request=request, name="checkout.html",
        context={"cart": cart_data, "error": None, "fulfillment_method": "delivery", "address": ""},
    )


@app.post("/shop/checkout")
def checkout_submit(
    request: Request,
    fulfillment_method: str = Form(...),
    address: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    try:
        order = create_order_from_cart(db, current_user.id, fulfillment_method, address)
    except HTTPException as e:
        cart = get_or_create_cart(db, current_user.id)
        cart_data = build_cart_response(db, cart)
        return templates.TemplateResponse(
            request=request, name="checkout.html",
            context={
                "cart": cart_data, "error": e.detail,
                "fulfillment_method": fulfillment_method, "address": address,
            },
            status_code=e.status_code,
        )
    return RedirectResponse(url=f"/shop/orders/{order.id}", status_code=303)


@app.get("/shop/orders/{order_id}")
def order_confirmation_page(
    order_id: int, request: Request, db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    try:
        order = get_user_order(db, current_user.id, order_id)
    except HTTPException:
        return templates.TemplateResponse(
            request=request, name="404.html",
            context={"message": "Заказ не найден"}, status_code=404,
        )
    return templates.TemplateResponse(
        request=request, name="order_confirmation.html", context={"order": order}
    )


@app.get("/")
def root():
    return {"message": "API магазина работает. /docs — Swagger, /shop — витрина."}