import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
    phone = Column(String, nullable=True)
    id_role = Column(Integer, ForeignKey("roles.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role_rel = relationship("RoleORM")

    @property
    def role(self):
        """Отдаёт имя роли строкой — так Pydantic-схема UserOut не замечает,
        что под капотом теперь FK на отдельную таблицу, а не enum-колонка."""
        return self.role_rel.role_name


class ItemORM(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    id_category = Column(Integer, ForeignKey("categories.id"), nullable=False)
    id_item_type = Column(Integer, ForeignKey("item_types.id"), nullable=False)
    stock_quantity = Column(Integer, nullable=True)
    duration_days = Column(Integer, nullable=True)

    category_rel = relationship("CategoryORM")
    item_type_rel = relationship("ItemTypeORM")

    @property
    def category(self):
        return self.category_rel.name

    @property
    def item_type(self):
        return self.item_type_rel.name