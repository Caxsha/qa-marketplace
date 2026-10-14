from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.backend.auth import decode_access_token
from app.backend.constants import STATUS_LABELS
from app.backend.database import SessionLocal
from app.backend.db_models import UserORM


def header_user_context(request: Request) -> dict:
    """Шапка узнаёт, авторизован ли пользователь и админ ли он."""
    token = request.cookies.get("access_token")
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return {"current_user": None}
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter(UserORM.id == user_id).first()
        if user is None:
            return {"current_user": None}
        return {"current_user": {"id": user.id, "login": user.login, "is_admin": user.role == "admin"}}
    finally:
        db.close()


templates = Jinja2Templates(directory="app/backend/templates", context_processors=[header_user_context])
templates.env.filters["status_label"] = lambda s: STATUS_LABELS.get(getattr(s, "value", s), str(s))