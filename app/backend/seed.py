import sys

from app.backend.database import engine, SessionLocal, Base
from app.backend.db_models import ItemORM, RoleORM, CategoryORM, ItemTypeORM
from app.backend.data import ITEMS


def get_or_create(model, db, **kwargs):
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    instance = model(**kwargs)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def validate_item_business_rule(item_type_name, stock_quantity, duration_days):
    """REQ-CAT-002a: проверка в коде, так как CHECK в БД не видит соседние таблицы."""
    if item_type_name == "product":
        if stock_quantity is None or stock_quantity < 0:
            raise ValueError("product требует stock_quantity >= 0")
        if duration_days is not None:
            raise ValueError("product не должен иметь duration_days")
    elif item_type_name == "service":
        if duration_days is None or duration_days <= 0:
            raise ValueError("service требует duration_days > 0")
        if stock_quantity is not None:
            raise ValueError("service не должен иметь stock_quantity")


def main(reset: bool = False):
    if reset:
        Base.metadata.drop_all(bind=engine)
        print("Все таблицы удалены")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        get_or_create(RoleORM, db, role_name="user")
        get_or_create(RoleORM, db, role_name="admin")

        if db.query(ItemORM).count() == 0:
            for item in ITEMS:
                validate_item_business_rule(
                    item["item_type"], item["stock_quantity"], item["duration_days"]
                )
                category = get_or_create(CategoryORM, db, name=item["category"])
                item_type = get_or_create(ItemTypeORM, db, name=item["item_type"])

                db.add(ItemORM(
                    id=item["id"],
                    name=item["name"],
                    description=item.get("description"),
                    price=item["price"],
                    id_category=category.id,
                    id_item_type=item_type.id,
                    stock_quantity=item["stock_quantity"],
                    duration_days=item["duration_days"],
                ))
            db.commit()
            print("Справочники и товары загружены")
        else:
            print("Таблица items уже содержит данные — пропускаю")
    finally:
        db.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)