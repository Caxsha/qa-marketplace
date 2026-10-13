import re
import secrets
from typing import Optional

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.backend.auth import hash_password, verify_password
from app.backend.db_models import UserORM

LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{5,20}$")
_email_adapter = TypeAdapter(EmailStr)


class ProfileError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _login_taken(db: Session, login: str, exclude_user_id: Optional[int] = None) -> bool:
    query = db.query(UserORM.id).filter(UserORM.login == login)
    if exclude_user_id is not None:
        query = query.filter(UserORM.id != exclude_user_id)
    return query.first() is not None


def generate_unique_login(db: Session, email: str) -> str:
    local_part = email.split("@")[0].lower()
    base = re.sub(r"[^a-z0-9._-]", "", local_part)[:20]
    if len(base) < 3:
        base = "user"

    if not _login_taken(db, base):
        return base
    for _ in range(20):
        candidate = f"{base}{secrets.randbelow(9000) + 1000}"
        if not _login_taken(db, candidate):
            return candidate
    return f"user{secrets.token_hex(4)}"


def ensure_login(db: Session, user: UserORM) -> UserORM:
    """Для пользователей, созданных до появления автогенерации."""
    if not user.login:
        user.login = generate_unique_login(db, user.email)
        db.commit()
        db.refresh(user)
    return user


def update_profile(db: Session, user: UserORM, login: str, email: str, phone: Optional[str]) -> None:
    login = (login or "").strip().lower()
    email = (email or "").strip()
    phone = (phone or "").strip() or None

    if not LOGIN_RE.match(login):
        raise ProfileError("Логин: 3–30 символов, только латинские буквы, цифры, точка, дефис и подчёркивание")
    if _login_taken(db, login, user.id):
        raise ProfileError("Этот логин уже занят", 409)

    # Формат проверяем только если email меняется: ранее созданные
    # аккаунты могут иметь email, прошедший только браузерную проверку
    if email != user.email:
        try:
            _email_adapter.validate_python(email)
        except ValidationError:
            raise ProfileError("Введите корректный email")
        if db.query(UserORM.id).filter(UserORM.email == email, UserORM.id != user.id).first():
            raise ProfileError("Этот email уже зарегистрирован", 409)

    if phone and not PHONE_RE.match(phone):
        raise ProfileError("Телефон: 5–20 символов, цифры, +, пробелы, дефисы и скобки")

    user.login = login
    user.email = email
    user.phone = phone
    db.commit()
    db.refresh(user)


def change_password(db: Session, user: UserORM, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ProfileError("Текущий пароль указан неверно")
    if len(new_password) < 8:
        raise ProfileError("Новый пароль должен содержать не менее 8 символов")
    user.password_hash = hash_password(new_password)
    db.commit()