import os
import secrets
import sys

from sqlalchemy import text

from app.backend.auth import hash_password
from app.backend.data import ITEMS
from app.backend.database import Base, SessionLocal, engine
from app.backend.db_models import CategoryORM, ItemORM, ItemTypeORM, RoleORM, UserORM
from app.backend.services.user_service import generate_unique_login

IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"


def seed_password(env_name: str, dev_default: str) -> str:
    """В разработке — удобный пароль по умолчанию, в production — своё значение или случайное."""
    value = os.getenv(env_name)
    if value:
        return value
    if IS_PRODUCTION:
        generated = secrets.token_urlsafe(12)
        print(f"[seed] {env_name} не задан. Сгенерирован пароль: {generated} (сохрани, второй раз он не покажется)")
        return generated
    return dev_default


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


def create_user_if_missing(db, email: str, password: str, role_name: str, phone=None):
    email = email.lower()
    if db.query(UserORM).filter(UserORM.email == email).first():
        print(f"Пользователь {email} уже существует, пропускаю")
        return
    role = db.query(RoleORM).filter(RoleORM.role_name == role_name).first()
    db.add(UserORM(
        email=email,
        login=generate_unique_login(db, email),
        password_hash=hash_password(password),
        phone=phone,
        id_role=role.id,
    ))
    db.commit()
    print(f"Создан {role_name}: {email}")


def main(reset: bool = False):
    if reset and IS_PRODUCTION and "--force" not in sys.argv:
        sys.exit("--reset в production удаляет все данные. Если это точно нужно, добавь --force")
    if IS_PRODUCTION and not os.getenv("SEED_ADMIN_EMAIL"):
        sys.exit("В production задай SEED_ADMIN_EMAIL (и желательно SEED_ADMIN_PASSWORD)")

    if reset:
        Base.metadata.drop_all(bind=engine)
        print("Все таблицы удалены")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        get_or_create(RoleORM, db, role_name="user")
        get_or_create(RoleORM, db, role_name="admin")

        if not IS_PRODUCTION:
            create_user_if_missing(
                db, os.getenv("SEED_USER_EMAIL", "user@example.com"),
                seed_password("SEED_USER_PASSWORD", "User12345"), "user", phone="+7 900 111-22-33",
            )
        create_user_if_missing(
            db, os.getenv("SEED_ADMIN_EMAIL", "admin@example.com"),
            seed_password("SEED_ADMIN_PASSWORD", "Admin12345"), "admin", phone="+7 900 444-55-66",
        )

        if db.query(ItemORM).count() == 0:
            for item in ITEMS:
                validate_item_business_rule(item["item_type"], item["stock_quantity"], item["duration_days"])
                category = get_or_create(CategoryORM, db, name=item["category"])
                item_type = get_or_create(ItemTypeORM, db, name=item["item_type"])
                db.add(ItemORM(
                    id=item["id"], name=item["name"], description=item.get("description"),
                    price=item["price"], id_category=category.id, id_item_type=item_type.id,
                    stock_quantity=item["stock_quantity"], duration_days=item["duration_days"],
                ))
            db.commit()
            if db.bind.dialect.name == "postgresql":
                db.execute(text(
                    "SELECT setval(pg_get_serial_sequence('items', 'id'), (SELECT MAX(id) FROM items))"
                ))
                db.commit()
            print("Справочники и товары загружены")
        else:
            print("Таблица items уже содержит данные, пропускаю")
    finally:
        db.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
