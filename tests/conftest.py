from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.backend.database import Base
from app.backend.db_models import (
    CategoryORM,
    ItemTypeORM,
    ItemORM,
    RoleORM,
    UserORM,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_shop_data(db_session: Session):
    role = RoleORM(role_name="user")
    category = CategoryORM(name="Продукты")
    item_type = ItemTypeORM(name="product")

    db_session.add_all([role, category, item_type])
    db_session.flush()

    user = UserORM(
        email="buyer@example.com",
        password_hash="secret",
        id_role=role.id,
    )

    item = ItemORM(
        name="Домашние яйца",
        price=Decimal("120.00"),
        id_category=category.id,
        id_item_type=item_type.id,
        stock_quantity=50,
        is_active=True,
    )

    db_session.add_all([user, item])
    db_session.commit()

    return {
        "user": user,
        "item": item,
    }