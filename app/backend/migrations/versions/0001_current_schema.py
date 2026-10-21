"""Create or upgrade the marketplace schema without dropping existing data.

Revision ID: 0001_current_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

from app.backend import db_models  # noqa: F401 - registers mapped tables
from app.backend.database import Base

revision = "0001_current_schema"
down_revision = None
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    names = {entry["name"] for entry in inspector.get_columns(table_name)}
    if column.name not in names:
        op.add_column(table_name, column)


def _has_unique_constraint(table_name: str, name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(
        item.get("name") == name
        for item in inspector.get_unique_constraints(table_name)
    )


def _has_unique_columns(table_name: str, columns: set[str]) -> bool:
    inspector = inspect(op.get_bind())
    return any(
        set(item.get("column_names") or []) == columns
        for item in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # These additions cover databases created before profile, catalog visibility,
    # and API idempotency fields were introduced.
    _add_column_if_missing("users", sa.Column("login", sa.String(), nullable=True))
    _add_column_if_missing("users", sa.Column("phone", sa.String(), nullable=True))
    _add_column_if_missing(
        "users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
    )
    _add_column_if_missing("items", sa.Column("description", sa.String(), nullable=True))
    _add_column_if_missing(
        "items",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column_if_missing(
        "orders",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    _add_column_if_missing(
        "orders", sa.Column("idempotency_key", sa.String(length=100), nullable=True)
    )

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("login", sa.String()),
    )
    rows = bind.execute(sa.select(users.c.id, users.c.login)).all()
    used = {login for _, login in rows if login}
    for user_id, login in rows:
        if login:
            continue
        candidate = f"user{user_id}"
        suffix = 1
        while candidate in used:
            candidate = f"user{user_id}_{suffix}"
            suffix += 1
        bind.execute(
            users.update().where(users.c.id == user_id).values(login=candidate)
        )
        used.add(candidate)

    if not _has_unique_columns("users", {"login"}):
        duplicates = bind.execute(text(
            "SELECT login FROM users GROUP BY login HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicates:
            raise RuntimeError("Cannot add unique login constraint: duplicate logins exist")
        op.create_unique_constraint("uq_users_login", "users", ["login"])

    if not _has_unique_constraint("orders", "uq_orders_user_idempotency_key"):
        op.create_unique_constraint(
            "uq_orders_user_idempotency_key", "orders", ["user_id", "idempotency_key"]
        )

    if bind.dialect.name == "postgresql":
        for table_name, column_name, precision in (
            ("items", "price", 12),
            ("orders", "total", 14),
            ("order_items", "price", 12),
        ):
            op.alter_column(
                table_name,
                column_name,
                type_=sa.Numeric(precision, 2),
                postgresql_using=f"{column_name}::numeric({precision}, 2)",
            )


def downgrade() -> None:
    raise RuntimeError("This data-preserving baseline migration is intentionally irreversible")
