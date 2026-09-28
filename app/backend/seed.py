from app.backend.database import engine, SessionLocal, Base
from app.backend.db_models import ItemORM, ItemTypeEnum
from app.backend.data import ITEMS

Base.metadata.create_all(bind=engine)

db = SessionLocal()

if db.query(ItemORM).count() == 0:
    for item in ITEMS:
        db.add(ItemORM(
            id=item["id"],
            name=item["name"],
            price=item["price"],
            category=item["category"],
            item_type=ItemTypeEnum(item["item_type"]),
            stock_quantity=item["stock_quantity"],
            duration_days=item["duration_days"],
        ))
    db.commit()
    print("Данные загружены в БД")
else:
    print("Таблица items уже содержит данные — пропускаю")

db.close()