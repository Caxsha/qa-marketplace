from decimal import Decimal
from typing import Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backend.constants import ALLOWED_TRANSITIONS
from app.backend.db_models import (
    CartORM, ItemORM, OrderORM, OrderItemORM, OrderStatusLogORM, UserORM,
)
from app.backend.models import OrderOut, OrderItemOut, OrderStatus
from app.backend.services.cart_service import get_or_create_cart

ALLOWED_FULFILLMENT = {"delivery", "pickup"}
MAX_ADDRESS_LEN = 300

def build_order_response(order: OrderORM) -> OrderOut:
    items_out = [
        OrderItemOut(
            item_id=oi.item_id, name=oi.name, item_type=oi.item_type,
            price=oi.price, quantity=oi.quantity, subtotal=oi.price * oi.quantity,
        )
        for oi in order.items_rel
    ]
    return OrderOut(
        id=order.id, user_id=order.user_id, items=items_out, total=order.total,
        fulfillment_method=order.fulfillment_method, address=order.address,
        status=order.status, created_at=order.created_at, updated_at=order.updated_at,
    )



def create_order_from_cart(
    db: Session,
    user_id: int,
    fulfillment_method: str,
    address: Optional[str],
    idempotency_key: Optional[str] = None,
) -> Tuple[OrderOut, bool]:
    fulfillment_method = (fulfillment_method or "").strip()
    if fulfillment_method not in ALLOWED_FULFILLMENT:
        raise HTTPException(status_code=422, detail="Invalid fulfillment method")

    address = (address or "").strip() or None
    if fulfillment_method == "delivery":
        if not address:
            raise HTTPException(
                status_code=400,
                detail="Address is required for delivery",
            )
        if len(address) > MAX_ADDRESS_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"Address is too long (max {MAX_ADDRESS_LEN})",
            )
    else:
        address = None

    cart = get_or_create_cart(db, user_id)
    db.query(CartORM).filter(CartORM.id == cart.id).with_for_update().populate_existing().first()
    db.expire(cart, ["items_rel"])

    if idempotency_key:
        existing = db.query(OrderORM).filter(
            OrderORM.user_id == user_id,
            OrderORM.idempotency_key == idempotency_key,
        ).first()
        if existing is not None:
            return build_order_response(existing), True

    if not cart.items_rel:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Блокируем строки товаров до конца оформления заказа.
    # Это предотвращает одновременное списание последних единиц товара.
    item_ids = sorted({ci.item_id for ci in cart.items_rel})
    locked = {
        item.id: item
        for item in (
            db.query(ItemORM)
            .filter(ItemORM.id.in_(item_ids))
            .order_by(ItemORM.id)
            .with_for_update()
            .populate_existing()
            .all()
        )
    }

    # REQ-ORD-002: проверка остатков товаров
    for ci in cart.items_rel:
        item = locked.get(ci.item_id)

        if item is None:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Item not found: {ci.item_id}",
            )

        if not item.is_active:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Item is no longer available: {item.name}",
            )

        if (
            item.item_type == "product"
            and item.stock_quantity is not None
            and ci.quantity > item.stock_quantity
        ):
            detail = f"Insufficient stock for item: {item.name}"
            db.rollback()
            raise HTTPException(status_code=400, detail=detail)

    total = sum(
        (locked[ci.item_id].price * ci.quantity for ci in cart.items_rel),
        Decimal("0.00"),
    )

    order = OrderORM(
        user_id=user_id,
        total=total,
        fulfillment_method=fulfillment_method,
        address=address,
        status="awaiting_payment",
        idempotency_key=idempotency_key,
    )
    db.add(order)
    db.flush()

    for ci in cart.items_rel:
        item = locked[ci.item_id]

        db.add(
            OrderItemORM(
                order_id=order.id,
                item_id=item.id,
                name=item.name,
                item_type=item.item_type,
                price=item.price,
                quantity=ci.quantity,
            )
        )

        if item.item_type == "product" and item.stock_quantity is not None:
            item.stock_quantity -= ci.quantity  # OQ-007

    for ci in list(cart.items_rel):
        db.delete(ci)  # REQ-ORD-001: очистка корзины

    db.commit()
    db.refresh(order)

    return build_order_response(order), False



def get_user_order(db: Session, user_id: int, order_id: int) -> OrderOut:
    order = db.query(OrderORM).filter(
        OrderORM.id == order_id, OrderORM.user_id == user_id
    ).first()
    if order is None:
        # Намеренно 404, не 403 — см. security-заметку OQ-009 в 05-api-contract.md
        raise HTTPException(status_code=404, detail="Order not found")
    return build_order_response(order)


def get_user_orders(db: Session, user_id: int):
    orders = (
        db.query(OrderORM)
        .filter(OrderORM.user_id == user_id)
        .order_by(OrderORM.created_at.desc())
        .all()
    )
    return [build_order_response(o) for o in orders]


def change_user_order_status(
    db: Session, user: UserORM, order_id: int, new_status: OrderStatus
) -> OrderOut:
    query = db.query(OrderORM).filter(OrderORM.id == order_id)
    if user.role != "admin":
        query = query.filter(OrderORM.user_id == user.id)
    order = query.with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    target = new_status.value
    allowed = ALLOWED_TRANSITIONS.get(order.status, []) if user.role == "admin" else []
    if user.role == "user" and order.status == "awaiting_payment":
        allowed = ["cancelled"]

    if target not in allowed:
        if user.role == "user" and target != "cancelled":
            raise HTTPException(status_code=403, detail="Not allowed to perform this transition")
        if user.role not in {"user", "admin"}:
            raise HTTPException(status_code=403, detail="Not allowed to perform this transition")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {order.status} → {target}",
        )

    old_status = order.status
    order.status = target
    db.add(OrderStatusLogORM(
        order_id=order.id,
        changed_by=user.id,
        from_status=old_status,
        to_status=target,
    ))
    db.commit()
    db.refresh(order)
    return build_order_response(order)
