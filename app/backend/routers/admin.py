from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.backend.auth import require_admin
from app.backend.constants import ALLOWED_TRANSITIONS, LOW_STOCK_THRESHOLD, ORDER_STATUSES
from app.backend.database import get_db
from app.backend.db_models import CategoryORM, ItemORM, UserORM
from app.backend.services import admin_service as svc
from app.backend.services.admin_service import AdminError
from app.backend.templating import templates

# include_in_schema=False: HTML-страницы не засоряют Swagger
router = APIRouter(prefix="/shop/admin", include_in_schema=False)

NOTICES = {
    "status": "Статус заказа обновлён ✓",
    "created": "Позиция добавлена ✓",
    "saved": "Изменения сохранены ✓",
    "toggled": "Видимость позиции изменена ✓",
    "stock": "Остаток обновлён ✓",
}


def not_found(request: Request, message: str):
    return templates.TemplateResponse(
        request=request, name="404.html", context={"message": message}, status_code=404
    )


# ---------- обзор ----------

@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), admin: UserORM = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request, name="admin/dashboard.html",
        context={"admin_tab": "dashboard", "stats": svc.get_dashboard_stats(db),
                 "threshold": LOW_STOCK_THRESHOLD},
    )


# ---------- заказы ----------

@router.get("/orders")
def orders_page(
    request: Request,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    selected = status if status in ORDER_STATUSES else ""
    return templates.TemplateResponse(
        request=request, name="admin/orders.html",
        context={
            "admin_tab": "orders", "orders": svc.list_orders(db, selected or None),
            "counts": svc.order_counts(db), "selected_status": selected, "statuses": ORDER_STATUSES,
        },
    )


def render_order(request: Request, db: Session, order_id: int, *, error=None, notice=None, status_code=200):
    try:
        order = svc.get_order_for_admin(db, order_id)
    except AdminError:
        return not_found(request, "Заказ не найден")
    return templates.TemplateResponse(
        request=request, name="admin/order_detail.html",
        context={
            "admin_tab": "orders", "order": order,
            "allowed": ALLOWED_TRANSITIONS.get(order.status, []),
            "error": error, "notice": notice,
        },
        status_code=status_code,
    )


@router.get("/orders/{order_id}")
def order_detail(
    order_id: int,
    request: Request,
    notice: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    return render_order(request, db, order_id, notice=NOTICES.get(notice))


@router.post("/orders/{order_id}/status")
def order_change_status(
    order_id: int,
    request: Request,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    try:
        order = svc.get_order_for_admin(db, order_id)
        svc.change_order_status(db, order, new_status, admin)
    except AdminError as e:
        if e.status_code == 404:
            return not_found(request, "Заказ не найден")
        return render_order(request, db, order_id, error=e.message, status_code=e.status_code)
    return RedirectResponse(url=f"/shop/admin/orders/{order_id}?notice=status", status_code=303)


# ---------- каталог ----------

def render_items(request: Request, db: Session, q: Optional[str] = None, *,
                 error=None, notice=None, status_code=200):
    return templates.TemplateResponse(
        request=request, name="admin/items.html",
        context={
            "admin_tab": "items", "items": svc.list_items_admin(db, q), "q": q or "",
            "threshold": LOW_STOCK_THRESHOLD, "error": error, "notice": notice,
        },
        status_code=status_code,
    )


@router.get("/items")
def items_page(
    request: Request,
    q: Optional[str] = Query(None),
    notice: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    return render_items(request, db, q, notice=NOTICES.get(notice))


def render_item_form(request: Request, db: Session, *, item=None, form=None, error=None, status_code=200):
    categories = db.query(CategoryORM).order_by(CategoryORM.name).all()
    if form is None:
        if item is not None:
            form = {
                "name": item.name,
                "description": item.description or "",
                "price": f"{item.price:.2f}".rstrip("0").rstrip("."),
                "category": item.category,
                "new_category": "",
                "item_type": item.item_type,
                "stock_quantity": "" if item.stock_quantity is None else item.stock_quantity,
                "duration_days": "" if item.duration_days is None else item.duration_days,
            }
        else:
            form = {
                "name": "", "description": "", "price": "",
                "category": categories[0].name if categories else "", "new_category": "",
                "item_type": "product", "stock_quantity": "", "duration_days": "",
            }
    return templates.TemplateResponse(
        request=request, name="admin/item_form.html",
        context={"admin_tab": "items", "item": item, "form": form,
                 "categories": categories, "error": error},
        status_code=status_code,
    )


@router.get("/items/new")
def item_new_page(request: Request, db: Session = Depends(get_db), admin: UserORM = Depends(require_admin)):
    return render_item_form(request, db)


@router.post("/items/new")
def item_create(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    price: str = Form(""),
    category: str = Form(""),
    new_category: str = Form(""),
    item_type: str = Form(""),
    stock_quantity: str = Form(""),
    duration_days: str = Form(""),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    form = {
        "name": name, "description": description, "price": price, "category": category,
        "new_category": new_category, "item_type": item_type,
        "stock_quantity": stock_quantity, "duration_days": duration_days,
    }
    try:
        svc.save_item(db, None, form)
    except AdminError as e:
        return render_item_form(request, db, form=form, error=e.message, status_code=e.status_code)
    return RedirectResponse(url="/shop/admin/items?notice=created", status_code=303)


@router.get("/items/{item_id}/edit")
def item_edit_page(item_id: int, request: Request, db: Session = Depends(get_db),
                   admin: UserORM = Depends(require_admin)):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        return not_found(request, "Позиция не найдена")
    return render_item_form(request, db, item=item)


@router.post("/items/{item_id}/edit")
def item_update(
    item_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    price: str = Form(""),
    category: str = Form(""),
    new_category: str = Form(""),
    stock_quantity: str = Form(""),
    duration_days: str = Form(""),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        return not_found(request, "Позиция не найдена")
    form = {
        "name": name, "description": description, "price": price, "category": category,
        "new_category": new_category, "item_type": item.item_type,
        "stock_quantity": stock_quantity, "duration_days": duration_days,
    }
    try:
        svc.save_item(db, item, form)
    except AdminError as e:
        return render_item_form(request, db, item=item, form=form, error=e.message,
                                status_code=e.status_code)
    return RedirectResponse(url="/shop/admin/items?notice=saved", status_code=303)


@router.post("/items/{item_id}/toggle")
def item_toggle(item_id: int, request: Request, db: Session = Depends(get_db),
                admin: UserORM = Depends(require_admin)):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        return not_found(request, "Позиция не найдена")
    item.is_active = not item.is_active
    db.commit()
    return RedirectResponse(url="/shop/admin/items?notice=toggled", status_code=303)


@router.post("/items/{item_id}/stock")
def item_stock(
    item_id: int,
    request: Request,
    stock_quantity: str = Form(""),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        return not_found(request, "Позиция не найдена")
    try:
        svc.set_stock(db, item, stock_quantity)
    except AdminError as e:
        return render_items(request, db, error=e.message, status_code=e.status_code)
    return RedirectResponse(url="/shop/admin/items?notice=stock", status_code=303)


# ---------- пользователи ----------

@router.get("/users")
def users_page(
    request: Request,
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_admin),
):
    return templates.TemplateResponse(
        request=request, name="admin/users.html",
        context={"admin_tab": "users", "rows": svc.list_users(db, q), "q": q or ""},
    )