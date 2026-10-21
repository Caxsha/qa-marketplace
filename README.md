# QA Marketplace

## Локальный запуск

Нужны Python 3.10+ и PostgreSQL. Создайте базу `qa_marketplace` и файл `.env` с `DATABASE_URL` и случайным `JWT_SECRET_KEY` длиной не менее 32 символов. Не добавляйте `.env` в Git.

Из корня проекта в PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r app/backend/requirements.txt
alembic upgrade head
python -m app.backend.seed
python run.py
```

Приложение запускается по адресу `http://127.0.0.1:8000`; Swagger UI доступен по `/docs`.

## База данных

Для существующей базы сначала сделайте резервную копию, затем выполните `alembic upgrade head`. Миграция сохраняет строки, добавляет отсутствующие поля профиля, видимости каталога, версии токена и идемпотентности заказа, а цены переводит на `NUMERIC`. Она намеренно не поддерживает автоматический downgrade.

`python -m app.backend.seed --reset` очищает и пересоздаёт данные; используйте эту команду только для локальной тестовой базы.

## Проверки

```powershell
python -m unittest discover -s tests
```

`app/backend/static/css/style.css` содержит общие стили магазина. Один файл подходит текущему небольшому приложению; выделяйте стили по страницам, когда появятся конфликты или отдельная сборка фронтенда.
