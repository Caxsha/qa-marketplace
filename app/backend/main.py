import os
from typing import List, Optional

from fastapi import FastAPI, Query, Depends, Request, HTTPException, Form, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.backend.models import Item, ItemType
from app.backend.services.items_service import query_items
from app.backend.services.cart_service import (
    get_or_create_cart,
    build_cart_response,
    add_item_to_cart,
    update_item_quantity,
    remove_item_from_cart,
)
from app.backend.routers.auth import router as auth_router
from app.backend.routers.cart import router as cart_router
from app.backend.routers.orders import router as orders_router
from app.backend.db_models import (
    ItemORM, CategoryORM, UserORM, RoleORM, CartORM,
)
from app.backend.database import get_db
from app.backend.auth import (
    AdminRequired,
    LoginRequired,
    authenticate,
    create_access_token,
    get_current_user_optional,
    hash_password,
    set_auth_cookie,
)
from app.backend.security import (
    MAX_BODY_BYTES,
    SAFE_METHODS,
    apply_security_headers,
    client_ip,
    login_limiter_email,
    login_limiter_ip,
    normalize_email,
    origin_is_trusted,
    register_limiter,
    validate_new_password,
)
from app.backend.services.order_service import (
    create_order_from_cart, get_user_order, get_user_orders,
)
from app.backend.services.user_service import (
    ProfileError, ensure_login, generate_unique_login, update_profile, change_password,
)
from app.backend.templating import templates
from app.backend.routers.admin import router as admin_router

APP_ENV = os.getenv("APP_ENV", "development").lower()
SHOW_DOCS = os.getenv(
    "ENABLE_DOCS", "false" if APP_ENV == "production" else "true"
).lower() == "true"

app = FastAPI(
    title="Магазин мамы",
    version="0.6.0",
    docs_url="/docs" if SHOW_DOCS else None,
    redoc_url="/redoc" if SHOW_DOCS else None,
    openapi_url="/openapi.json" if SHOW_DOCS else None,
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    try:
        body_size = int(request.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        body_size = 0

    if body_size > MAX_BODY_BYTES:
        response = PlainTextResponse("Запрос слишком большой", status_code=413)
        apply_security_headers(request, response)
        return response

    auth_header = request.headers.get("authorization", "")
    uses_bearer = auth_header.lower().startswith("bearer ")
    uses_session_cookie = "access_token" in request.cookies and not uses_bearer

    # Проверяем источник изменяющих запросов, которые могут использовать cookie.
    if (
        request.method not in SAFE_METHODS
        and uses_session_cookie
        and not origin_is_trusted(request)
    ):
        response = PlainTextResponse(
            "Запрос отклонён: чужой источник", status_code=403
        )
        apply_security_headers(request, response)
        return response

    response = await call_next(request)
    apply_security_headers(request, response)
    return response

app.mount("/static", StaticFiles(directory="app/backend/static"), name="static")

app.include_router(auth_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(admin_router)

@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(url="/shop/login", status_code=303)

@app.exception_handler(AdminRequired)
async def admin_required_handler(request: Request, exc: AdminRequired):
    return templates.TemplateResponse(request=request, name="403.html", context={}, status_code=403)


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
    item = db.query(ItemORM).filter(ItemORM.id == item_id, ItemORM.is_active.is_(True)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# --- Web: витрина, каталог, карточка товара ---

@app.get("/shop")
def shop_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(ItemORM).filter(ItemORM.is_active.is_(True)).order_by(ItemORM.id).all()
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
    item = db.query(ItemORM).filter(ItemORM.id == item_id, ItemORM.is_active.is_(True)).first()
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
    email = email.strip().lower()[:254]
    ip = client_ip(request)

    if login_limiter_ip.is_blocked(ip) or login_limiter_email.is_blocked(email):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Слишком много неудачных попыток. Попробуйте позже."},
            status_code=429,
        )

    user = db.query(UserORM).filter(func.lower(UserORM.email) == email).first()
    if not authenticate(user, password):
        login_limiter_ip.hit(ip)
        login_limiter_email.hit(email)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Неверный email или пароль"},
            status_code=401,
        )

    login_limiter_email.reset(email)
    response = RedirectResponse(url="/shop", status_code=303)
    set_auth_cookie(response, request, create_access_token(user.id, user.token_version))
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
    agree: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    def fail(message: str, code: int = 400):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": message},
            status_code=code,
        )

    ip = client_ip(request)
    if register_limiter.is_blocked(ip):
        return fail("Слишком много попыток регистрации. Попробуйте позже.", 429)
    register_limiter.hit(ip)

    if not agree:
        return fail("Необходимо принять политику конфиденциальности и оферту")

    try:
        email = normalize_email(email)
        validate_new_password(password)
    except ValueError as e:
        return fail(str(e))

    existing = db.query(UserORM.id).filter(
        func.lower(UserORM.email) == email
    ).first()
    if existing:
        return fail("Этот email уже зарегистрирован", 409)

    default_role = db.query(RoleORM).filter(RoleORM.role_name == "user").first()
    if default_role is None:
        return fail("Не удалось создать пользователя: роль user не настроена.", 500)

    user = UserORM(
        email=email,
        login=generate_unique_login(db, email),
        password_hash=hash_password(password),
        id_role=default_role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = RedirectResponse(url="/shop", status_code=303)
    set_auth_cookie(response, request, create_access_token(user.id, user.token_version))
    return response


# --- Web: личный кабинет ---

NOTICES = {
    "profile": "Профиль сохранён ✓",
    "password": "Пароль изменён ✓",
}


def render_account(request: Request, db: Session, user: UserORM, *, error=None,
                   error_section=None, notice=None, form=None, status_code: int = 200):
    ensure_login(db, user)
    orders = get_user_orders(db, user.id)
    total_spent = sum(o.total for o in orders if o.status != "cancelled")
    form = form or {"login": user.login, "email": user.email, "phone": user.phone or ""}
    return templates.TemplateResponse(
        request=request, name="account.html",
        context={
            "user": user, "orders": orders, "total_spent": total_spent, "form": form,
            "error": error, "error_section": error_section, "notice": notice,
        },
        status_code=status_code,
    )

INFO_PAGES = {
    "delivery": "Доставка и оплата",
    "returns": "Возврат и обмен",
    "privacy": "Политика конфиденциальности",
    "offer": "Публичная оферта",
}


@app.get("/shop/info/{slug}")
def info_page(slug: str, request: Request):
    title = INFO_PAGES.get(slug)
    if title is None:
        return templates.TemplateResponse(
            request=request, name="404.html",
            context={"message": "Страница не найдена"}, status_code=404,
        )
    return templates.TemplateResponse(
        request=request, name="info.html", context={"slug": slug, "title": title}
    )


@app.get("/shop/account")
def account_page(
    request: Request,
    notice: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    return render_account(request, db, current_user, notice=NOTICES.get(notice))


@app.post("/shop/account/profile")
def account_profile_submit(
    request: Request,
    login: str = Form(""),
    email: str = Form(""),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    try:
        update_profile(db, current_user, login, email, phone)
    except ProfileError as e:
        form = {"login": login, "email": email, "phone": phone or ""}
        return render_account(request, db, current_user, error=e.message,
                              error_section="profile", form=form, status_code=e.status_code)
    return RedirectResponse(url="/shop/account?notice=profile", status_code=303)


@app.post("/shop/account/password")
def account_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/shop/login", status_code=303)
    try:
        change_password(db, current_user, current_password, new_password)
    except ProfileError as e:
        return render_account(request, db, current_user, error=e.message,
                              error_section="password", status_code=e.status_code)
    response = RedirectResponse(url="/shop/account?notice=password", status_code=303)
    set_auth_cookie(response, request, create_access_token(current_user.id, current_user.token_version))
    return response


@app.post("/shop/logout")
def logout_web():
    response = RedirectResponse(url="/shop", status_code=303)
    response.delete_cookie("access_token")
    return response


# --- Web: корзина ---

def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"

ERROR_TRANSLATIONS = {
    "Cart is empty": "Корзина пуста",
    "Address is required for delivery": "Укажите адрес доставки",
    "Item not found": "Товар не найден",
}

def ru_error(detail: str) -> str:
    if detail.startswith("Insufficient stock: only"):
        left = detail.rsplit("only", 1)[1].replace("left", "").strip()
        return f"Недостаточно товара на складе: осталось {left} шт."
    if detail.startswith("Insufficient stock for item:"):
        return "Недостаточно товара на складе: " + detail.split(":", 1)[1].strip()
    if detail.startswith("Item is no longer available:"):
        return "Позиция больше недоступна: " + detail.split(":", 1)[1].strip()
    return ERROR_TRANSLATIONS.get(detail, detail)


def login_redirect(request: Request):
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": "/shop/login"})
    return RedirectResponse(url="/shop/login", status_code=303)

def cart_count_value(db: Session, user_id: int) -> int:
    cart = db.query(CartORM).filter(CartORM.user_id == user_id).first()
    return sum(ci.quantity for ci in cart.items_rel) if cart else 0


def toast(request: Request, message: str, kind: str = "success", count: Optional[int] = None):
    return templates.TemplateResponse(
        request=request, name="_toast.html",
        context={"message": message, "kind": kind, "count": count},
    )


def cart_partial(request: Request, db: Session, user_id: int):
    cart_data = build_cart_response(db, get_or_create_cart(db, user_id))
    count = sum(ci.quantity for ci in cart_data.items)
    return templates.TemplateResponse(
        request=request, name="_cart_partial.html",
        context={"cart": cart_data, "count": count},
    )


@app.get("/shop/cart/count")
def cart_count(
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return HTMLResponse("", headers={"Cache-Control": "no-store"})
    count = cart_count_value(db, current_user.id)
    return HTMLResponse(str(count) if count else "", headers={"Cache-Control": "no-store"})


@app.post("/shop/cart/add")
def cart_add_web(
    request: Request,
    item_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return login_redirect(request)
    try:
        add_item_to_cart(db, current_user.id, item_id, quantity)
    except HTTPException as e:
        if is_htmx(request):
            return toast(request, ru_error(e.detail), "error")
        raise
    if is_htmx(request):
        return toast(request, "Добавлено в корзину ✓", count=cart_count_value(db, current_user.id))
    return RedirectResponse(url="/shop/cart", status_code=303)


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


@app.post("/shop/cart/update/{item_id}")
def cart_update_web(
    item_id: int,
    request: Request,
    action: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return login_redirect(request)
    cart = get_or_create_cart(db, current_user.id)
    current_item = next((ci for ci in cart.items_rel if ci.item_id == item_id), None)
    if current_item is not None:
        new_qty = current_item.quantity + 1 if action == "increase" else max(1, current_item.quantity - 1)
        try:
            update_item_quantity(db, current_user.id, item_id, new_qty)
        except HTTPException:
            pass
    if is_htmx(request):
        return cart_partial(request, db, current_user.id)
    return RedirectResponse(url="/shop/cart", status_code=303)


@app.post("/shop/cart/remove/{item_id}")
def cart_remove_web(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[UserORM] = Depends(get_current_user_optional),
):
    if current_user is None:
        return login_redirect(request)
    try:
        remove_item_from_cart(db, current_user.id, item_id)
    except HTTPException:
        pass
    if is_htmx(request):
        return cart_partial(request, db, current_user.id)
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
        order, _ = create_order_from_cart(db, current_user.id, fulfillment_method, address)
    except HTTPException as e:
        cart = get_or_create_cart(db, current_user.id)
        cart_data = build_cart_response(db, cart)
        return templates.TemplateResponse(
            request=request, name="checkout.html",
            context={
                "cart": cart_data, "error": ru_error(e.detail),
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
