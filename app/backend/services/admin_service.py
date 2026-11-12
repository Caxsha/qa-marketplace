from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.backend.constants import (
    ALLOWED_TRANSITIONS, LOW_STOCK_THRESHOLD, ORDER_STATUSES, STATUS_LABELS,
)
from app.backend.db_models import (
    CategoryORM, ItemORM, ItemTypeORM, OrderORM, OrderStatusLogORM, PaymentORM, UserORM,
)
from app.backend.security import like_escape
from app.backend.services.payment_service import (
    cancel_pending_demo_payments, restore_order_inventory,
)


class AdminError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------- заказы ----------

def order_counts(db: Session) -> dict:
    rows = dict(db.query(OrderORM.status, func.count(OrderORM.id)).group_by(OrderORM.status).all())
    counts = {status: rows.get(status, 0) for status in ORDER_STATUSES}
    counts["all"] = sum(counts.values())
    return counts


def list_orders(db: Session, status: Optional[str] = None):
    query = db.query(OrderORM).order_by(OrderORM.created_at.desc(), OrderORM.id.desc())
    if status in ORDER_STATUSES:
        query = query.filter(OrderORM.status == status)
    return query.all()


def get_order_for_admin(db: Session, order_id: int) -> OrderORM:
    order = db.query(OrderORM).filter(OrderORM.id == order_id).first()
    if order is None:
        raise AdminError("Заказ не найден", 404)
    return order


def change_order_status(db: Session, order: OrderORM, new_status: str, admin: UserORM) -> None:
    if new_status not in ORDER_STATUSES:
        raise AdminError("Неизвестный статус заказа", 422)

    old_status = order.status
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, []):
        raise AdminError(
            f"Недопустимый переход: {STATUS_LABELS.get(old_status, old_status)} → {STATUS_LABELS[new_status]}",
            400,
        )

    order.status = new_status
    if new_status == "cancelled":
        cancel_pending_demo_payments(db, order)
        restore_order_inventory(db, order)
    db.add(OrderStatusLogORM(
        order_id=order.id, changed_by=admin.id, from_status=old_status, to_status=new_status,
    ))
    db.commit()


# ---------- обзор ----------

def _demo_revenue(db: Session, *conditions) -> Decimal:
    total = db.query(func.coalesce(func.sum(PaymentORM.amount), Decimal("0.00"))).filter(
        PaymentORM.provider == "demo", PaymentORM.status == "succeeded", *conditions
    ).scalar()
    return total or Decimal("0.00")


def get_dashboard_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    month_start = today_start.replace(day=1)
    next_month_start = month_start.replace(
        year=month_start.year + (month_start.month == 12),
        month=1 if month_start.month == 12 else month_start.month + 1,
    )
    low_stock = (
        db.query(ItemORM)
        .filter(
            ItemORM.is_active.is_(True),
            ItemORM.stock_quantity.isnot(None),
            ItemORM.stock_quantity <= LOW_STOCK_THRESHOLD,
        )
        .order_by(ItemORM.stock_quantity, ItemORM.id)
        .all()
    )
    recent_orders = db.query(OrderORM).order_by(OrderORM.created_at.desc(), OrderORM.id.desc()).limit(5).all()
    method_rows = dict(
        db.query(PaymentORM.payment_method, func.count(PaymentORM.id))
        .filter(PaymentORM.provider == "demo", PaymentORM.status == "succeeded")
        .group_by(PaymentORM.payment_method).all()
    )
    return {
        "counts": order_counts(db),
        "revenue_today": _demo_revenue(
            db, PaymentORM.paid_at >= today_start, PaymentORM.paid_at < tomorrow_start
        ),
        "revenue_month": _demo_revenue(
            db, PaymentORM.paid_at >= month_start, PaymentORM.paid_at < next_month_start
        ),
        "revenue_total": _demo_revenue(db),
        "demo_payment_methods": {
            "card": method_rows.get("card", 0),
            "sbp": method_rows.get("sbp", 0),
        },
        "users_count": db.query(func.count(UserORM.id)).scalar(),
        "low_stock": low_stock,
        "recent_orders": recent_orders,
    }


# ---------- каталог ----------

def _parse_int(value, field: str, minimum: int) -> int:
    text = str(value if value is not None else "").strip()
    try:
        number = int(text)
    except ValueError:
        raise AdminError(f"{field}: введите целое число")
    if number < minimum:
        raise AdminError(f"{field}: значение не может быть меньше {minimum}")
    if number > 1_000_000:
        raise AdminError(f"{field}: слишком большое значение")
    return number


def _parse_price(value) -> Decimal:
    text = str(value if value is not None else "").strip().replace(",", ".")
    try:
        price = Decimal(text)
    except InvalidOperation:
        raise AdminError("Цена: введите число")
    if not price.is_finite() or price <= 0 or price > Decimal("1000000"):
        raise AdminError("Цена: от 0.01 до 1 000 000 ₽")
    return price.quantize(Decimal("0.01"))


def list_items_admin(db: Session, search: Optional[str] = None):
    query = db.query(ItemORM).order_by(ItemORM.id)
    if search and search.strip():
        pattern = f"%{like_escape(search.strip()[:100])}%"
        query = query.filter(ItemORM.name.ilike(pattern, escape="\\"))
    return query.all()


def set_stock(db: Session, item: ItemORM, value) -> None:
    if item.item_type != "product":
        raise AdminError("Остаток есть только у товаров", 400)
    item.stock_quantity = _parse_int(value, "Остаток", 0)
    db.commit()


def save_item(db: Session, item: Optional[ItemORM], form: dict) -> ItemORM:
    """Создаёт позицию (item=None) или обновляет существующую.
    Правило REQ-CAT-002a: у товара обязателен остаток, у услуги — срок выполнения."""
    name = (form.get("name") or "").strip()
    if not name:
        raise AdminError("Название обязательно")
    if len(name) > 120:
        raise AdminError("Название не длиннее 120 символов")

    description = (form.get("description") or "").strip() or None
    if description and len(description) > 2000:
        raise AdminError("Описание не длиннее 2000 символов")

    price = _parse_price(form.get("price"))

    category_name = (form.get("new_category") or "").strip() or (form.get("category") or "").strip()
    if not category_name:
        raise AdminError("Выберите категорию или введите новую")
    if len(category_name) > 50:
        raise AdminError("Название категории не длиннее 50 символов")

    # Тип существующей позиции не меняется
    item_type = item.item_type if item is not None else (form.get("item_type") or "")
    if item_type not in ("product", "service"):
        raise AdminError("Выберите тип позиции")

    if item_type == "product":
        stock_quantity = _parse_int(form.get("stock_quantity"), "Остаток", 0)
        duration_days = None
    else:
        duration_days = _parse_int(form.get("duration_days"), "Срок выполнения (дней)", 1)
        stock_quantity = None

    category = db.query(CategoryORM).filter(
        func.lower(CategoryORM.name) == category_name.lower()
    ).first()
    if category is None:
        category = CategoryORM(name=category_name)
        db.add(category)
        db.flush()
    type_row = db.query(ItemTypeORM).filter(ItemTypeORM.name == item_type).first()

    fields = dict(
        name=name, description=description, price=price,
        id_category=category.id, id_item_type=type_row.id,
        stock_quantity=stock_quantity, duration_days=duration_days,
    )
    if item is None:
        item = ItemORM(is_active=True, **fields)
        db.add(item)
    else:
        for key, value in fields.items():
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


# ---------- пользователи ----------

def list_users(db: Session, search: Optional[str] = None):
    query = (
        db.query(UserORM, func.count(OrderORM.id))
        .outerjoin(OrderORM, OrderORM.user_id == UserORM.id)
        .group_by(UserORM.id)
        .order_by(UserORM.id)
    )
    if search and search.strip():
        pattern = f"%{like_escape(search.strip()[:100])}%"
        query = query.filter(or_(
            UserORM.email.ilike(pattern, escape="\\"),
            UserORM.login.ilike(pattern, escape="\\"),
        ))
    return query.all()
