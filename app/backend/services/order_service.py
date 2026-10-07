from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backend.db_models import OrderORM, OrderItemORM
from app.backend.models import OrderOut, OrderItemOut
from app.backend.services.cart_service import get_or_create_cart


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
        status=order.status, created_at=order.created_at,
    )


def create_order_from_cart(
    db: Session, user_id: int, fulfillment_method: str, address: Optional[str]
) -> OrderOut:
    cart = get_or_create_cart(db, user_id)
    if not cart.items_rel:
        raise HTTPException(status_code=400, detail="Cart is empty")

    if fulfillment_method == "delivery" and not address:
        raise HTTPException(status_code=400, detail="Address is required for delivery")

    # REQ-ORD-002: проверка остатка перед созданием заказа
    for ci in cart.items_rel:
        item = ci.item_rel
        if item.item_type == "product" and item.stock_quantity is not None and ci.quantity > item.stock_quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for item: {item.name}")

    total = sum(ci.item_rel.price * ci.quantity for ci in cart.items_rel)

    order = OrderORM(
        user_id=user_id, total=total, fulfillment_method=fulfillment_method,
        address=address if fulfillment_method == "delivery" else None,
        status="awaiting_payment",
    )
    db.add(order)
    db.flush()  # получить order.id до commit

    for ci in cart.items_rel:
        item = ci.item_rel
        db.add(OrderItemORM(
            order_id=order.id, item_id=item.id, name=item.name,
            item_type=item.item_type, price=item.price, quantity=ci.quantity,
        ))
        if item.item_type == "product" and item.stock_quantity is not None:
            item.stock_quantity -= ci.quantity  # OQ-007

    for ci in list(cart.items_rel):
        db.delete(ci)  # REQ-ORD-001: корзина очищается после заказа

    db.commit()
    db.refresh(order)
    return build_order_response(order)


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