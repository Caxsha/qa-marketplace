from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.backend.db_models import CartORM, CartItemORM, ItemORM
from app.backend.models import CartOut, CartItemOut


def get_or_create_cart(db: Session, user_id: int) -> CartORM:
    cart = db.query(CartORM).filter(CartORM.user_id == user_id).first()
    if cart is None:
        cart = CartORM(user_id=user_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def build_cart_response(db: Session, cart: CartORM) -> CartOut:
    items_out: List[CartItemOut] = []
    total = 0.0
    for ci in cart.items_rel:
        item = ci.item_rel
        subtotal = item.price * ci.quantity
        total += subtotal
        items_out.append(CartItemOut(
            item_id=item.id,
            name=item.name,
            item_type=item.item_type,
            price=item.price,
            quantity=ci.quantity,
            subtotal=subtotal,
        ))
    return CartOut(id=cart.id, user_id=cart.user_id, items=items_out, total=total)


def add_item_to_cart(db: Session, user_id: int, item_id: int, quantity: int = 1) -> CartOut:
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    cart = get_or_create_cart(db, user_id)
    existing = db.query(CartItemORM).filter(
        CartItemORM.cart_id == cart.id, CartItemORM.item_id == item_id
    ).first()

    if item.item_type == "service":
        # OQ-011 открыт: количество услуги фиксировано на 1
        if existing is None:
            db.add(CartItemORM(cart_id=cart.id, item_id=item_id, quantity=1))
            db.commit()
        return build_cart_response(db, cart)

    new_quantity = (existing.quantity if existing else 0) + quantity
    if item.stock_quantity is not None and new_quantity > item.stock_quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock: only {item.stock_quantity} left")

    if existing:
        existing.quantity = new_quantity
    else:
        db.add(CartItemORM(cart_id=cart.id, item_id=item_id, quantity=new_quantity))
    db.commit()
    return build_cart_response(db, cart)


def update_item_quantity(db: Session, user_id: int, item_id: int, quantity: int) -> CartOut:
    cart = get_or_create_cart(db, user_id)
    cart_item = db.query(CartItemORM).filter(
        CartItemORM.cart_id == cart.id, CartItemORM.item_id == item_id
    ).first()
    if cart_item is None:
        raise HTTPException(status_code=404, detail="Item not in cart")

    item = cart_item.item_rel
    if item.item_type == "service":
        return build_cart_response(db, cart)

    if quantity < 1:
        raise HTTPException(status_code=422, detail="quantity must be >= 1")
    if item.stock_quantity is not None and quantity > item.stock_quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock: only {item.stock_quantity} left")

    cart_item.quantity = quantity
    db.commit()
    return build_cart_response(db, cart)


def remove_item_from_cart(db: Session, user_id: int, item_id: int) -> CartOut:
    cart = get_or_create_cart(db, user_id)
    cart_item = db.query(CartItemORM).filter(
        CartItemORM.cart_id == cart.id, CartItemORM.item_id == item_id
    ).first()
    if cart_item is None:
        raise HTTPException(status_code=404, detail="Item not in cart")

    db.delete(cart_item)
    db.commit()
    return build_cart_response(db, cart)