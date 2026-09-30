from app.backend.database import engine, SessionLocal, Base
from app.backend.db_models import ItemORM, RoleORM, CategoryORM, ItemTypeORM
from app.backend.data import ITEMS

Base.metadata.create_all(bind=engine)

db = SessionLocal()


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
    """Проверка REQ-CAT-002a на уровне кода, раз не можем сделать это CHECK'ом в БД."""
    if item_type_name == "product":
        assert stock_quantity is not None and stock_quantity >= 0, \
            "product требует stock_quantity >= 0"
        assert duration_days is None, "product не должен иметь duration_days"
    elif item_type_name == "service":
        assert duration_days is not None and duration_days > 0, \
            "service требует duration_days > 0"
        assert stock_quantity is None, "service не должен иметь stock_quantity"


# Справочник ролей — нужен до регистрации первого пользователя
get_or_create(RoleORM, db, role_name="user")
get_or_create(RoleORM, db, role_name="admin")

if db.query(ItemORM).count() == 0:
    for item in ITEMS:
        validate_item_business_rule(item["item_type"], item["stock_quantity"], item["duration_days"])

        category = get_or_create(CategoryORM, db, name=item["category"])
        item_type = get_or_create(ItemTypeORM, db, name=item["item_type"])

        db.add(ItemORM(
            id=item["id"],
            name=item["name"],
            description=item["description"],
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

db.close()