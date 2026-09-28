from typing import List, Optional
from fastapi import FastAPI, Query, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.backend.models import Item, ItemType
from app.backend.db_models import ItemORM
from app.backend.database import get_db
from app.backend.routers.auth import router as auth_router

app = FastAPI(title="Магазин мамы", version="0.4.0")

app.mount("/static", StaticFiles(directory="app/backend/static"), name="static")
templates = Jinja2Templates(directory="app/backend/templates")

app.include_router(auth_router)


@app.get("/api/items", response_model=List[Item], tags=["items"])
def get_items(
    item_type: Optional[ItemType] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ItemORM)
    if item_type is not None:
        query = query.filter(ItemORM.item_type == item_type.value)
    return query.all()


@app.get("/api/items/{item_id}", response_model=Item, tags=["items"])
def get_item(item_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    item = db.query(ItemORM).filter(ItemORM.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/shop")
def shop_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(ItemORM).all()
    return templates.TemplateResponse(
        request=request,
        name="items.html",
        context={"items": items}
    )


@app.get("/")
def root():
    return {"message": "API магазина работает. /docs — Swagger, /shop — витрина."}