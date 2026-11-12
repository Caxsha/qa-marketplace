"""Add fields for local simulated payment records.

Revision ID: 0003_demo_payment_ledger
Revises: 0002_yookassa_payments
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_demo_payment_ledger"
down_revision = "0002_yookassa_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "payments" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("payments")}
    if "provider" not in existing:
        op.add_column("payments", sa.Column(
            "provider", sa.String(), nullable=False, server_default="legacy",
        ))
    if "payment_method" not in existing:
        op.add_column("payments", sa.Column(
            "payment_method", sa.String(), nullable=False, server_default="unknown",
        ))
    if "currency" not in existing:
        op.add_column("payments", sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="RUB",
        ))
    if "paid_at" not in existing:
        op.add_column("payments", sa.Column(
            "paid_at", sa.DateTime(timezone=True), nullable=True,
        ))


def downgrade() -> None:
    op.drop_column("payments", "paid_at")
    op.drop_column("payments", "currency")
    op.drop_column("payments", "payment_method")
    op.drop_column("payments", "provider")
