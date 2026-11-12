import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backend.db_models import (
    ItemORM, OrderORM, OrderStatusLogORM, PaymentORM,
)

DEMO_PAYMENT_METHODS = {"card", "sbp"}


def demo_payments_enabled() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() != "production"


def create_demo_payment(db: Session, order: OrderORM) -> PaymentORM | None:
    if not demo_payments_enabled():
        return None
    payment = PaymentORM(
        order_id=order.id,
        attempt_key=str(uuid4()),
        provider="demo",
        payment_method="unknown",
        status="pending",
        amount=order.total,
        currency="RUB",
    )
    db.add(payment)
    return payment


def simulate_payment(db: Session, order_id: int, user_id: int, method: str) -> PaymentORM:
    if not demo_payments_enabled():
        raise HTTPException(status_code=404, detail="Демо-оплата отключена")
    if method not in DEMO_PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="Неизвестный способ демо-оплаты")

    order = db.query(OrderORM).filter(
        OrderORM.id == order_id, OrderORM.user_id == user_id,
    ).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    payment = db.query(PaymentORM).filter(
        PaymentORM.order_id == order.id,
        PaymentORM.provider == "demo",
    ).order_by(PaymentORM.id.desc()).with_for_update().first()

    if order.status == "paid" and payment and payment.status == "succeeded":
        return payment
    if order.status != "awaiting_payment":
        raise HTTPException(status_code=409, detail="Заказ нельзя оплатить в текущем статусе")

    if payment is None:
        payment = create_demo_payment(db, order)
    payment.payment_method = method
    payment.status = "succeeded"
    payment.paid_at = datetime.now(timezone.utc)
    order.status = "paid"
    db.add(OrderStatusLogORM(
        order_id=order.id, changed_by=None,
        from_status="awaiting_payment", to_status="paid",
    ))
    db.commit()
    db.refresh(payment)
    return payment


def cancel_pending_demo_payments(db: Session, order: OrderORM) -> None:
    for payment in order.payments_rel:
        if payment.provider == "demo" and payment.status == "pending":
            payment.status = "canceled"


def restore_order_inventory(db: Session, order: OrderORM) -> None:
    if order.inventory_released:
        return
    item_ids = [row.item_id for row in order.items_rel if row.item_id is not None]
    items = {
        item.id: item for item in db.query(ItemORM).filter(ItemORM.id.in_(item_ids)).with_for_update().all()
    } if item_ids else {}
    for row in order.items_rel:
        item = items.get(row.item_id)
        if item and item.item_type == "product" and item.stock_quantity is not None:
            item.stock_quantity += row.quantity
    order.inventory_released = True


