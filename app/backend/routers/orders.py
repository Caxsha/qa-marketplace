from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.backend.auth import get_current_user
from app.backend.database import get_db
from app.backend.db_models import UserORM
from app.backend.models import CreateOrderRequest, OrderOut, OrderStatusUpdate
from app.backend.services.order_service import (
    change_user_order_status,
    create_order_from_cart,
    get_user_order,
    get_user_orders,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut)
def create_order(
    payload: CreateOrderRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user),
):
    key = idempotency_key.strip() if idempotency_key else None
    order, replayed = create_order_from_cart(
        db,
        current_user.id,
        payload.fulfillment_method.value,
        payload.address,
        key or None,
    )
    response.status_code = 200 if replayed else 201
    return order


@router.get("", response_model=List[OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user),
):
    return get_user_orders(db, current_user.id)


@router.get("/{order_id}", response_model=OrderOut)
def read_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user),
):
    return get_user_order(db, current_user.id, order_id)


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user),
):
    return change_user_order_status(db, current_user, order_id, payload.status)
