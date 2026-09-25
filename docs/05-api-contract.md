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
