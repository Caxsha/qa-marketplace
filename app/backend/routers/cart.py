from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.database import get_db
from app.backend.db_models import UserORM
from app.backend.auth import get_current_user
from app.backend.models import CartOut
from app.backend.services.cart_service import (
    get_or_create_cart, build_cart_response, add_item_to_cart,
    update_item_quantity, remove_item_from_cart,
)

router = APIRouter(prefix="/api/cart", tags=["cart"])


class AddCartItemRequest(BaseModel):
    item_id: int
    quantity: int = 1


class UpdateCartItemRequest(BaseModel):
    quantity: int


@router.get("", response_model=CartOut)
def get_cart(db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    cart = get_or_create_cart(db, current_user.id)
    return build_cart_response(db, cart)


@router.post("/items", response_model=CartOut, status_code=201)
def add_cart_item(payload: AddCartItemRequest, db: Session = Depends(get_db),
                   current_user: UserORM = Depends(get_current_user)):
    return add_item_to_cart(db, current_user.id, payload.item_id, payload.quantity)


@router.patch("/items/{item_id}", response_model=CartOut)
def update_cart_item(item_id: int, payload: UpdateCartItemRequest, db: Session = Depends(get_db),
                      current_user: UserORM = Depends(get_current_user)):
    return update_item_quantity(db, current_user.id, item_id, payload.quantity)


@router.delete("/items/{item_id}", response_model=CartOut)
def delete_cart_item(item_id: int, db: Session = Depends(get_db),
                      current_user: UserORM = Depends(get_current_user)):
    return remove_item_from_cart(db, current_user.id, item_id)