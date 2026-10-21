import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backend.database import Base
from app.backend.db_models import (
    CartItemORM, CartORM, CategoryORM, ItemORM, ItemTypeORM,
    OrderORM, OrderStatusLogORM, PaymentORM, RoleORM, UserORM,
)
from app.backend.models import OrderStatus
from app.backend.services.order_service import change_user_order_status, create_order_from_cart
from app.backend.services.payment_service import simulate_payment


class DemoPaymentServiceTests(unittest.TestCase):
    def setUp(self):
        self.app_env = patch.dict(os.environ, {"APP_ENV": "development"})
        self.app_env.start()
        self.addCleanup(self.app_env.stop)

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

        user_role = RoleORM(role_name="user")
        admin_role = RoleORM(role_name="admin")
        category = CategoryORM(name="Food")
        product_type = ItemTypeORM(name="product")
        self.db.add_all([user_role, admin_role, category, product_type])
        self.db.flush()
        self.user = UserORM(email="buyer@example.com", password_hash="x", id_role=user_role.id)
        self.other_user = UserORM(email="other@example.com", password_hash="x", id_role=user_role.id)
        self.admin = UserORM(email="admin@example.com", password_hash="x", id_role=admin_role.id)
        self.db.add_all([self.user, self.other_user, self.admin])
        self.db.flush()

        self.item = ItemORM(
            name="Bread", price=Decimal("12.35"), id_category=category.id,
            id_item_type=product_type.id, stock_quantity=5, is_active=True,
        )
        self.db.add(self.item)
        self.db.flush()
        cart = CartORM(user_id=self.user.id)
        self.db.add(cart)
        self.db.flush()
        self.db.add(CartItemORM(cart_id=cart.id, item_id=self.item.id, quantity=2))
        self.db.commit()

    def create_order(self):
        order, replayed = create_order_from_cart(self.db, self.user.id, "pickup", None)
        self.assertFalse(replayed)
        return self.db.get(OrderORM, order.id)

    def test_order_starts_with_pending_demo_payment(self):
        order = self.create_order()
        payment = self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).one()

        self.assertEqual(order.status, "awaiting_payment")
        self.assertEqual(payment.provider, "demo")
        self.assertEqual(payment.status, "pending")
        self.assertEqual(payment.payment_method, "unknown")
        self.assertEqual(payment.amount, Decimal("24.70"))
        self.assertEqual(payment.currency, "RUB")
        self.assertIsNone(payment.paid_at)

    def test_card_payment_succeeds_and_repeat_is_idempotent(self):
        order = self.create_order()

        first = simulate_payment(self.db, order.id, self.user.id, "card")
        second = simulate_payment(self.db, order.id, self.user.id, "card")

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.payment_method, "card")
        self.assertEqual(first.status, "succeeded")
        self.assertIsNotNone(first.paid_at)
        self.assertEqual(self.db.get(OrderORM, order.id).status, "paid")
        self.assertEqual(
            self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).count(), 1
        )
        self.assertEqual(
            self.db.query(OrderStatusLogORM).filter(
                OrderStatusLogORM.order_id == order.id,
                OrderStatusLogORM.to_status == "paid",
            ).count(), 1,
        )

    def test_sbp_payment_is_recorded_as_demo(self):
        order = self.create_order()

        payment = simulate_payment(self.db, order.id, self.user.id, "sbp")

        self.assertEqual(payment.provider, "demo")
        self.assertEqual(payment.payment_method, "sbp")
        self.assertEqual(payment.status, "succeeded")

    def test_unknown_method_is_rejected_without_changing_payment(self):
        order = self.create_order()

        with self.assertRaises(HTTPException) as raised:
            simulate_payment(self.db, order.id, self.user.id, "bank_transfer")

        self.assertEqual(raised.exception.status_code, 422)
        payment = self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).one()
        self.assertEqual(payment.status, "pending")
        self.assertEqual(self.db.get(OrderORM, order.id).status, "awaiting_payment")

    def test_other_user_cannot_simulate_order_payment(self):
        order = self.create_order()

        with self.assertRaises(HTTPException) as raised:
            simulate_payment(self.db, order.id, self.other_user.id, "card")

        self.assertEqual(raised.exception.status_code, 404)
        payment = self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).one()
        self.assertEqual(payment.status, "pending")

    def test_cancelled_order_cannot_be_paid_and_inventory_is_restored(self):
        order = self.create_order()
        change_user_order_status(self.db, self.user, order.id, OrderStatus.CANCELLED)

        with self.assertRaises(HTTPException) as raised:
            simulate_payment(self.db, order.id, self.user.id, "card")

        self.assertEqual(raised.exception.status_code, 409)
        payment = self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).one()
        self.assertEqual(payment.status, "canceled")
        self.assertEqual(self.db.get(ItemORM, self.item.id).stock_quantity, 5)

    def test_production_mode_disables_demo_payment_creation_and_capture(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            order, _ = create_order_from_cart(self.db, self.user.id, "pickup", None)

            with self.assertRaises(HTTPException) as raised:
                simulate_payment(self.db, order.id, self.user.id, "card")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(
            self.db.query(PaymentORM).filter(PaymentORM.order_id == order.id).count(), 0
        )
        self.assertEqual(self.db.get(OrderORM, order.id).status, "awaiting_payment")


if __name__ == "__main__":
    unittest.main()
