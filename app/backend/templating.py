from datetime import datetime

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.backend.auth import decode_access_token
from app.backend.constants import STATUS_LABELS
from app.backend.database import SessionLocal
from app.backend.db_models import UserORM
from app.backend.shop_config import SHOP

# Иконка категории по названию. Для новых категорий из админки берётся basket
CATEGORY_ICONS = {
    "Яйца": "egg",
    "Выпечка": "bakery",
    "Оформление": "party",
    "Консультации": "chef",
    "Другое": "basket",
}


def _current_user_for_header(request: Request):
    """Кто вошёл: нужно шапке и подвалу. Возвращает словарь или None."""
    token = request.cookies.get("access_token")
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter(UserORM.id == user_id).first()
        if user is None:
            return None
        return {"id": user.id, "login": user.login, "is_admin": user.role == "admin"}
    finally:
        db.close()


def template_context(request: Request) -> dict:
    """Общие данные для всех шаблонов: пользователь, настройки магазина, год."""
    return {
        "current_user": _current_user_for_header(request),
        "shop": SHOP,
        "current_year": datetime.now().year,
    }


def icon(name: str, extra_class: str = "") -> Markup:
    """SVG-иконка из static/icons/<name>.svg. Красится цветом текста (currentColor)."""
    safe_name = "".join(ch for ch in str(name) if ch.isalnum() or ch in "-_")
    classes = ("icon " + extra_class).strip()
    return Markup(
        f'<span class="{escape(classes)}" '
        f'style="--icon:url(/static/icons/{safe_name}.svg)" aria-hidden="true"></span>'
    )


def category_icon(category_name: str) -> str:
    return CATEGORY_ICONS.get(category_name, "basket")


templates = Jinja2Templates(
    directory="app/backend/templates",
    context_processors=[template_context],
)
templates.env.filters["status_label"] = lambda s: STATUS_LABELS.get(getattr(s, "value", s), str(s))
templates.env.globals["icon"] = icon
templates.env.globals["category_icon"] = category_icon