"""Historical schema migration for payment tracking and inventory release.

The revision identifier is retained because databases may already record it.

Revision ID: 0002_yookassa_payments
Revises: 0001_current_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_yookassa_payments"
down_revision = "0001_current_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("orders")}
    if "inventory_released" not in existing:
        op.add_column("orders", sa.Column(
            "inventory_released", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
    if "npd_receipt_issued_at" not in existing:
        op.add_column("orders", sa.Column(
            "npd_receipt_issued_at", sa.DateTime(timezone=True), nullable=True,
        ))
    if "payments" not in inspector.get_table_names():
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("provider_payment_id", sa.String(), nullable=True, unique=True),
            sa.Column("idempotence_key", sa.String(), nullable=False, unique=True),
            sa.Column("status", sa.String(), nullable=False, server_default="creating"),
            sa.Column("confirmation_url", sa.String(), nullable=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_payments_order_id", "payments", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")
    op.drop_column("orders", "npd_receipt_issued_at")
    op.drop_column("orders", "inventory_released")
