import os
import threading
import time
from typing import Deque, Dict
from collections import deque
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Request, Response
from pydantic import EmailStr, TypeAdapter, ValidationError

load_dotenv()

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_BYTES = 72          # ограничение bcrypt: остальное он молча отбрасывает
MAX_BODY_BYTES = 1_000_000
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TRUSTED_HOSTS = {h.strip() for h in os.getenv("TRUSTED_ORIGINS", "").split(",") if h.strip()}

_email_adapter = TypeAdapter(EmailStr)


# ---------- проверка входных данных ----------

def normalize_email(raw: str) -> str:
    email = (raw or "").strip()
    if len(email) > 254:
        raise ValueError("Email слишком длинный")
    try:
        _email_adapter.validate_python(email)
    except ValidationError:
        raise ValueError("Введите корректный email")
    return email.lower()   # OQ-003: регистр email не важен


def validate_new_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LEN:
        raise ValueError("Пароль должен содержать не менее 8 символов")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError("Пароль слишком длинный: не более 72 байт (около 36 русских букв)")


def like_escape(value: str) -> str:
    """Делает % и _ в поиске обычными символами (используй вместе с escape="\\")."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------- ограничение частоты запросов ----------

class RateLimiter:
    """Не более `limit` событий за `window_seconds` на ключ. Хранится в памяти процесса:
    подходит для одного воркера, при нескольких нужен общий Redis."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return False
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if not hits:
                del self._hits[key]
                return False
            return len(hits) >= self.limit

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 5000:   # чтобы перебором ключей нельзя было забить память
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
            self._hits.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_limiter_ip = RateLimiter(limit=20, window_seconds=600)     # 20 неудач с одного IP за 10 минут
login_limiter_email = RateLimiter(limit=5, window_seconds=900)   # 5 неудач на один email за 15 минут
register_limiter = RateLimiter(limit=10, window_seconds=3600)    # 10 попыток регистрации с IP в час


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- CSRF: запрос, меняющий данные, должен прийти с нашего сайта ----------

def origin_is_trusted(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return True   # браузер всегда шлёт Origin при POST; без него это curl/Postman, а не атака через браузер
    netloc = urlparse(source).netloc
    allowed = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")} | TRUSTED_HOSTS
    return netloc != "" and netloc in allowed


# ---------- защитные заголовки ----------

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://placehold.co",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])

PRIVATE_PREFIXES = ("/shop/account", "/shop/admin", "/shop/cart", "/shop/checkout", "/shop/orders")


def apply_security_headers(request: Request, response: Response) -> None:
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    h["Content-Security-Policy"] = CSP
    if request.url.scheme == "https":
        h["Strict-Transport-Security"] = "max-age=15552000"
    if request.url.path.startswith(PRIVATE_PREFIXES):
        h["Cache-Control"] = "no-store"   # после выхода кнопка «Назад» не покажет чужие данные