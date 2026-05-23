# RAG PACK site + Telegram bot

Статический сайт показывает каталог и отправляет заявки на backend. Backend принимает заявки с сайта, сохраняет их в SQLite и уведомляет админов через одного Telegram-бота. Если клиент пишет боту напрямую, бот показывает каталог и собирает заказ внутри Telegram.

## Frontend

Перед публикацией сайта замените API URL в `index.html`:

```html
<meta name="ragpack-api-url" content="https://your-backend-domain.example/api/orders" />
```

Токен бота нельзя добавлять в `index.html`, `script.js` или другие frontend-файлы.

## Backend

1. Перевыпустите токен бота через BotFather.
2. Создайте `backend/.env` по примеру `backend/.env.example`.
3. Укажите Telegram ID админов через запятую:

```env
BOT_TOKEN=replace_with_new_botfather_token
ADMIN_IDS=123456789,987654321
CORS_ORIGINS=https://your-github-pages-domain.example
```

4. Запустите сервис на VPS:

```bash
docker compose up -d --build
```

SQLite база хранится в Docker volume `ragpack-data`.

## Local checks

```bash
python3 -m compileall backend
node --check script.js
python3 -m json.tool catalog.json
```
