import os
import re

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


_phone = _env("SHOP_PHONE", "+7 (900) 123-45-67")

SHOP = {
    "name": "Магазин мамы",
    "tagline": "Домашние продукты и услуги с любовью — от Надежды для вас и ваших близких.",
    "phone": _phone,
    "phone_href": "tel:+" + re.sub(r"\D", "", _phone),
    "email": _env("SHOP_EMAIL"),
    "telegram": _env("SHOP_TELEGRAM"),    # например, https://t.me/username
    "whatsapp": _env("SHOP_WHATSAPP"),    # например, https://wa.me/79001234567
    "vk": _env("SHOP_VK"),
    "city": "Москва",
    "pickup_note": "самовывоз по договорённости",
    "hours": "Пн–Сб, 9:00–19:00",
    # Пока не заполнено, строка с данными продавца в подвале не показывается
    "seller_status": _env("SHOP_SELLER_STATUS", "Самозанятая (НПД)"),
    "seller_name": _env("SHOP_SELLER_NAME"),
    "seller_inn": _env("SHOP_SELLER_INN"),
    # true — на правовых страницах показывается пометка «черновик»
    "legal_draft": _env("SHOP_LEGAL_DRAFT", "true").lower() != "false",
}