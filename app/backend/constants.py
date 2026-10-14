STATUS_LABELS = {
    "awaiting_payment": "Ожидает оплаты",
    "paid": "Оплачен",
    "completed": "Выполнен",
    "cancelled": "Отменён",
}

ORDER_STATUSES = list(STATUS_LABELS)

# Разрешённые переходы для администратора (05-api-contract.md, PATCH /api/orders/{id}/status):
# awaiting_payment → paid, paid → completed, любой статус кроме completed → cancelled
ALLOWED_TRANSITIONS = {
    "awaiting_payment": ["paid", "cancelled"],
    "paid": ["completed", "cancelled"],
    "completed": [],
    "cancelled": [],
}

LOW_STOCK_THRESHOLD = 5