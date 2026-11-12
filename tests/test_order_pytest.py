from decimal import Decimal

from sqlalchemy.orm import Session

from app.backend.db_models import CartORM, CartItemORM, ItemORM
from app.backend.models import OrderStatus
from app.backend.services.order_service import create_order_from_cart


def test_create_order_from_cart_success(
    db_session: Session,
    sample_shop_data,
):
    user = sample_shop_data["user"]
    item = sample_shop_data["item"]

    cart = CartORM(user_id=user.id)
    db_session.add(cart)
    db_session.flush()

    cart_item = CartItemORM(
        cart_id=cart.id,
        item_id=item.id,
        quantity=3,
    )
    db_session.add(cart_item)
    db_session.commit()

    order, replayed = create_order_from_cart(
        db=db_session,
        user_id=user.id,
        fulfillment_method="pickup",
        address=None,
    )

    assert replayed is False
    assert order is not None
    assert order.user_id == user.id
    assert order.status == OrderStatus.AWAITING_PAYMENT
    assert order.total == Decimal("360.00")

    assert len(order.items) == 1
    assert order.items[0].name == "Домашние яйца"
    assert order.items[0].quantity == 3
    assert order.items[0].price == Decimal("120.00")
    assert order.items[0].subtotal == Decimal("360.00")

    db_session.refresh(item)

    assert item.stock_quantity == 47