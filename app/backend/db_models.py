from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, expression

from app.backend.database import Base


class RoleORM(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String, unique=True, nullable=False)


class CategoryORM(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)


class ItemTypeORM(Base):
    __tablename__ = "item_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)


class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    phone = Column(String, nullable=True)
    id_role = Column(Integer, ForeignKey("roles.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role_rel = relationship("RoleORM")

    @property
    def role(self):
        return self.role_rel.role_name


class ItemORM(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    id_category = Column(Integer, ForeignKey("categories.id"), nullable=False)
    id_item_type = Column(Integer, ForeignKey("item_types.id"), nullable=False)
    stock_quantity = Column(Integer, nullable=True)
    duration_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=expression.true())

    category_rel = relationship("CategoryORM")
    item_type_rel = relationship("ItemTypeORM")

    @property
    def category(self):
        return self.category_rel.name

    @property
    def item_type(self):
        return self.item_type_rel.name


class CartORM(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    items_rel = relationship("CartItemORM", cascade="all, delete-orphan", order_by="CartItemORM.id")


class CartItemORM(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    item_rel = relationship("ItemORM")


class OrderORM(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total = Column(Numeric(14, 2), nullable=False)
    fulfillment_method = Column(String, nullable=False)
    address = Column(String, nullable=True)
    status = Column(String, nullable=False, default="awaiting_payment")
    idempotency_key = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_rel = relationship("UserORM")
    items_rel = relationship("OrderItemORM", cascade="all, delete-orphan", order_by="OrderItemORM.id")
    status_log_rel = relationship("OrderStatusLogORM", cascade="all, delete-orphan",
                                  order_by="OrderStatusLogORM.id")


class OrderItemORM(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    name = Column(String, nullable=False)
    item_type = Column(String, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    quantity = Column(Integer, nullable=False)


class OrderStatusLogORM(Base):
    """Журнал: кто, когда и из какого статуса в какой перевёл заказ."""
    __tablename__ = "order_status_log"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    from_status = Column(String, nullable=False)
    to_status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    changed_by_rel = relationship("UserORM")
