from typing import List, Optional
from sqlalchemy.orm import Session

from app.backend.db_models import ItemORM, ItemTypeORM, CategoryORM


def query_items(
    db: Session,
    item_type: Optional[str] = None,
    categories: Optional[List[str]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    search: Optional[str] = None,
):
    """Единая точка фильтрации каталога. Используется и /api/items (JSON),
    и /shop/catalog (HTML) — см. 03-architecture.md: одна бизнес-логика,
    два представления."""
    query = (
        db.query(ItemORM)
        .join(ItemTypeORM, ItemORM.id_item_type == ItemTypeORM.id)
        .join(CategoryORM, ItemORM.id_category == CategoryORM.id)
    )

    if item_type:
        query = query.filter(ItemTypeORM.name == item_type)
    if categories:
        query = query.filter(CategoryORM.name.in_(categories))
    if min_price is not None:
        query = query.filter(ItemORM.price >= min_price)
    if max_price is not None:
        query = query.filter(ItemORM.price <= max_price)
    if search:
        query = query.filter(ItemORM.name.ilike(f"%{search}%"))

    return query.order_by(ItemORM.id).all()
