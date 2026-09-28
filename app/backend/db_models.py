import enum
from sqlalchemy import (
    Column, Integer, String, Float, Enum as SAEnum, DateTime, CheckConstraint
)
from sqlalchemy.sql import func

from app.backend.database import Base


class ItemTypeEnum(str, enum.Enum):
    PRODUCT = "product"
    SERVICE = "service"


class RoleEnum(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class ItemORM(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            "(item_type = 'product' AND stock_quantity >= 0 AND duration_days IS NULL) OR "
            "(item_type = 'service' AND duration_days > 0 AND stock_quantity IS NULL)",
            name="ck_item_type_fields",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    item_type = Column(
        SAEnum(ItemTypeEnum, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    stock_quantity = Column(Integer, nullable=True)
    duration_days = Column(Integer, nullable=True)


class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(
        SAEnum(RoleEnum, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=RoleEnum.USER,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())