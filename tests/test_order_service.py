import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backend.database import Base
from app.backend.auth import create_access_token, token_matches_user
from app.backend.db_models import (
    CartItemORM, CategoryORM, ItemORM, ItemTypeORM, OrderORM, PaymentORM, RoleORM, UserORM,
)
from app.backend.models import OrderStatus
from app.backend.services.order_service import (
    change_user_order_status, create_order_from_cart, get_user_order,
)


class OrderServiceTests(unittest.TestCase):
    def setUp(self):
        self.app_env = patch.dict(os.environ, {"APP_ENV": "development"})
        self.app_env.start()
        self.addCleanup(self.app_env.stop)

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        role = RoleORM(role_name="user")
        admin_role = RoleORM(role_name="admin")
        category = CategoryORM(name="Food")
        product_type = ItemTypeORM(name="product")
        self.db.add_all([role, admin_role, category, product_type])
        self.db.flush()
        self.user = UserORM(email="user@example.com", password_hash="x", id_role=role.id)
        self.admin = UserORM(email="admin@example.com", password_hash="x", id_role=admin_role.id)
        self.other_user = UserORM(email="other@example.com", password_hash="x", id_role=role.id)
        self.db.add_all([self.user, self.admin, self.other_user])
        self.db.flush()
        self.item = ItemORM(
            name="Bread", price=Decimal("12.35"), id_category=category.id,
            id_item_type=product_type.id, stock_quantity=5, is_active=True,
        )
        self.db.add(self.item)
        self.db.flush()
        self.cart = self.user_cart()
        self.db.add(CartItemORM(cart_id=self.cart.id, item_id=self.item.id, quantity=2))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def user_cart(self):
        from app.backend.db_models import CartORM
        cart = CartORM(user_id=self.user.id)
        self.db.add(cart)
        self.db.flush()
        return cart

    def test_create_order_saves_decimal_total_and_decrements_stock(self):
        order, replayed = create_order_from_cart(self.db, self.user.id, "pickup", None)
        self.assertFalse(replayed)
        self.assertEqual(order.total, Decimal("24.70"))
        self.assertEqual(self.db.get(ItemORM, self.item.id).stock_quantity, 3)
        self.assertEqual(self.cart.items_rel, [])

    def test_idempotency_key_returns_existing_order(self):
        first, replayed = create_order_from_cart(
            self.db, self.user.id, "pickup", None, "checkout-1"
        )
        second, replayed_again = create_order_from_cart(
            self.db, self.user.id, "pickup", None, "checkout-1"
        )
        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.get(ItemORM, self.item.id).stock_quantity, 3)
        self.assertEqual(
            self.db.query(PaymentORM).filter(PaymentORM.order_id == first.id).count(), 1
        )

    def test_hidden_item_is_not_ordered_or_decremented(self):
        self.item.is_active = False
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            create_order_from_cart(self.db, self.user.id, "pickup", None)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.db.get(ItemORM, self.item.id).stock_quantity, 5)
        self.assertEqual(len(self.cart.items_rel), 1)

    def test_user_can_cancel_pending_order_but_cannot_mark_paid(self):
        order, _ = create_order_from_cart(self.db, self.user.id, "pickup", None)
        with self.assertRaises(HTTPException) as raised:
            change_user_order_status(self.db, self.user, order.id, OrderStatus.PAID)
        self.assertEqual(raised.exception.status_code, 403)
        cancelled = change_user_order_status(
            self.db, self.user, order.id, OrderStatus.CANCELLED
        )
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)
        payment = self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).one()
        self.assertEqual(payment.status, "canceled")
        self.assertEqual(self.db.get(ItemORM, self.item.id).stock_quantity, 5)

    def test_admin_status_flow_and_owner_isolation(self):
        order, _ = create_order_from_cart(self.db, self.user.id, "pickup", None)
        paid = change_user_order_status(self.db, self.admin, order.id, OrderStatus.PAID)
        complete = change_user_order_status(
            self.db, self.admin, order.id, OrderStatus.COMPLETED
        )
        self.assertEqual(paid.status, OrderStatus.PAID)
        self.assertEqual(complete.status, OrderStatus.COMPLETED)
        with self.assertRaises(HTTPException) as raised:
            get_user_order(self.db, self.other_user.id, order.id)
        self.assertEqual(raised.exception.status_code, 404)

    def test_password_version_invalidates_previously_issued_tokens(self):
        old_token = create_access_token(self.user.id, self.user.token_version)
        self.assertTrue(token_matches_user(old_token, self.user))
        self.user.token_version += 1
        self.db.commit()
        self.assertFalse(token_matches_user(old_token, self.user))


if __name__ == "__main__":
    unittest.main()
