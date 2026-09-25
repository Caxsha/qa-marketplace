# QA Marketplace — API Contract v1.0

## Общие соглашения

- Формат данных: JSON (`Content-Type: application/json`).
- Аутентификация: JWT, срок жизни токена — 24 часа. Refresh-токен не входит в v1.
- Передача токена: заголовок `Authorization: Bearer <token>` ИЛИ httpOnly cookie `access_token`
  (см. `03-architecture.md`, раздел "Аутентификация").
- Пароль никогда не возвращается в ответах API (REQ-AUTH-002).
- Общий формат ошибки, если не указано иное:
```json
  { "detail": "Текст ошибки" }
```

## User — модель данных

| Поле | Тип | Описание |
|---|---|---|
| id | int | Уникальный идентификатор |
| email | string | Уникальный, используется для входа |
| password_hash | string | Хранится только в БД, никогда не отдаётся через API |
| role | string | `user` \| `admin`, по умолчанию `user` |
| created_at | datetime | Дата регистрации |

---

## POST /api/auth/register

Регистрация нового пользователя (REQ-AUTH-001).

**Request headers:** нет (публичный endpoint)

**Request body:**
```json
{
  "email": "danil@example.com",
  "password": "SecurePass123"
}
```

**Response 201 Created:**
```json
{
  "id": 1,
  "email": "danil@example.com",
  "role": "user",
  "created_at": "2026-09-25T10:00:00Z"
}
```

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 400 | Некорректный формат email | `{"detail": "Invalid email format"}` |
| 400 | Пароль короче 8 символов | `{"detail": "Password must be at least 8 characters"}` |
| 409 | Email уже зарегистрирован | `{"detail": "Email already registered"}` |
| 422 | Отсутствует обязательное поле | стандартный FastAPI validation error |

---

## POST /api/auth/login

Авторизация пользователя (REQ-AUTH-002).

**Request headers:** нет

**Request body:**
```json
{
  "email": "danil@example.com",
  "password": "SecurePass123"
}
```

**Response 200 OK:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```
Дополнительно сервер устанавливает httpOnly cookie `access_token` с теми же данными
(для клиентов `/shop`).

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 401 | Неверный email или пароль | `{"detail": "Invalid credentials"}` |
| 422 | Отсутствует обязательное поле | стандартный FastAPI validation error |

> Важно для QA: сообщение об ошибке одинаковое и для "email не найден", и для "пароль неверный" —
> это намеренно (REQ-AUTH-002), чтобы не давать подсказку о том, зарегистрирован ли email.
> Это отдельный security-тест на будущее.

---

## POST /api/auth/logout

Завершение сессии (REQ-AUTH-003).

**Request headers:** `Authorization: Bearer <token>` ИЛИ cookie `access_token`

**Request body:** нет

**Response 200 OK:**
```json
{ "detail": "Logged out" }
```

Сервер очищает cookie `access_token` (если она была установлена). Поскольку JWT в v1
stateless (без чёрного списка токенов), для клиентов на Bearer-токене логаут — это
ответственность клиента: он должен сам удалить токен у себя. Это ограничение v1,
фиксируем как техническое допущение, не как баг.

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 401 | Токен отсутствует или невалиден | `{"detail": "Not authenticated"}` |

---

## GET /api/users/me

Получить данные текущего авторизованного пользователя. Пригодится и для `/shop` (показать
"Привет, Данил" в шапке), и как удобный способ проверить, что токен вообще валиден.

**Request headers:** `Authorization: Bearer <token>` ИЛИ cookie `access_token`

**Response 200 OK:**
```json
{
  "id": 1,
  "email": "danil@example.com",
  "role": "user",
  "created_at": "2026-09-25T10:00:00Z"
}
```

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 401 | Токен отсутствует или невалиден | `{"detail": "Not authenticated"}` |

---

## Item — модель данных

| Поле | Тип | Описание |
|---|---|---|
| id | int | Уникальный идентификатор |
| name | string | Название позиции |
| price | float | Цена в рублях |
| category | string | Категория (например, `eggs`, `baking`, `services`) |
| item_type | string | `product` \| `service` |
| stock_quantity | int \| null | Только для `product`, ≥ 0 (REQ-CAT-002a) |
| duration_days | int \| null | Только для `service`, > 0 (REQ-CAT-002a) |

> **Допущение v1:** отдельного CRUD для управления товарами через API нет.
> Каталог наполняется через `seed.py` / напрямую через pgAdmin. Admin-CRUD
> (`POST/PUT/DELETE /api/items`) — кандидат на v2, вместе с полноценной ролью admin в UI.

---

## GET /api/items

Список позиций каталога (REQ-CAT-001, REQ-CAT-003, REQ-CAT-004).
Доступен без авторизации (OQ-001).

**Request headers:** нет

**Query-параметры (все необязательные):**

| Параметр | Тип | Описание |
|---|---|---|
| item_type | string | Фильтр `product` \| `service` |
| category | string | Фильтр по категории |
| min_price | float | Нижняя граница цены |
| max_price | float | Верхняя граница цены |
| search | string | Поиск по названию, без учёта регистра (REQ-CAT-003, OQ-004) |

**Response 200 OK:**
```json
[
  {
    "id": 1,
    "name": "Яйца куриные (десяток)",
    "price": 120,
    "category": "eggs",
    "item_type": "product",
    "stock_quantity": 50,
    "duration_days": null
  },
  {
    "id": 4,
    "name": "Оформление праздничного стола",
    "price": 3500,
    "category": "services",
    "item_type": "service",
    "stock_quantity": null,
    "duration_days": 2
  }
]
```
Пустой каталог или отсутствие совпадений по фильтру — это не ошибка: возвращается `200 OK` с `[]`.

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 422 | Некорректное значение параметра (например, `item_type=banana`) | стандартный FastAPI validation error |

---

## GET /api/items/{id}

Карточка одной позиции (REQ-CAT-005).

**Request headers:** нет

**Response 200 OK:**
```json
{
  "id": 1,
  "name": "Яйца куриные (десяток)",
  "price": 120,
  "category": "eggs",
  "item_type": "product",
  "stock_quantity": 50,
  "duration_days": null
}
```

**Errors:**

| Код | Причина | Body |
|---|---|---|
| 404 | Позиция с таким id не существует | `{"detail": "Item not found"}` |
| 422 | id не является целым числом | стандартный FastAPI validation error |

> **QA-заметка:** `GET /shop/items/{id}` (HTML-версия той же карточки, см. `03-architecture.md`)
> должна при отсутствии товара отдавать не JSON 404, а полноценную HTML-страницу с сообщением
> "Товар не найден" и тем же кодом 404 в заголовке ответа. Это отдельный тест-кейс на согласованность
> API и UI.
