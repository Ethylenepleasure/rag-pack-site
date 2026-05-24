# RAG PACK site + Telegram bot

Сайт показывает каталог, принимает заявки, отдает профиль клиента и админку CRM с того же домена, где работает backend. Backend сохраняет заявки в SQLite и уведомляет админов через одного Telegram-бота. Если клиент пишет боту напрямую, бот показывает каталог, собирает заказ внутри Telegram и может выдать код для входа на сайт.

## Frontend

По умолчанию сайт отправляет заявки на тот же домен:

```html
<meta name="ragpack-api-url" content="/api/orders" />
```

Если сайт опубликован отдельно от backend, замените значение на API-домен,
например `https://api.your-domain.example/api/orders`.

Токен бота нельзя добавлять в `index.html`, `script.js` или другие frontend-файлы.

## Backend

1. Перевыпустите токен бота через BotFather.
2. Создайте `backend/.env` по примеру `backend/.env.example`.
3. Укажите Telegram ID админов через запятую:

```env
BOT_TOKEN=replace_with_new_botfather_token
BOT_URL=https://t.me/ragpackleather_bot
ADMIN_IDS=123456789,987654321
CORS_ORIGINS=https://your-domain.example
DOMAIN=your-domain.example
MAX_REQUEST_SIZE=8192
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW_SECONDS=60
NOTIFICATION_QUEUE_SIZE=100
SECURE_COOKIES=true
```

4. Направьте DNS `DOMAIN` на VPS. Caddy автоматически выпустит HTTPS-сертификат.

5. Запустите сервис на VPS:

```bash
docker compose up -d --build
```

SQLite база хранится в Docker volume `ragpack-data`.
Backend отдает `/`, `/profile`, `/admin`, ассеты и API. Наружу смотрит Caddy
на 80/443 и проксирует запросы в контейнер приложения.

## Профиль и админка

- `/profile` открывает личный кабинет клиента. Для входа клиент переходит в
  Telegram-бота через кнопку на странице, делится контактом, получает 6-значный
  код и вводит его на сайте.
- `/admin` использует тот же вход, но доступен только Telegram ID из `ADMIN_IDS`.
- Код действует 10 минут, сессия в `HttpOnly` cookie живет 30 дней.

## Production guards

- `CORS_ORIGINS` обязателен и должен содержать только реальные домены сайта.
- `SECURE_COOKIES=true` нужен для production HTTPS. Для локального HTTP можно
  временно поставить `SECURE_COOKIES=false`.
- `/api/orders` ограничен по размеру JSON и числу заявок с одного IP.
- Telegram-уведомления отправляются из фоновой очереди, поэтому медленный Telegram
  не держит HTTP-запрос открытым.
- SQLite работает в WAL-режиме с `busy_timeout`, что снижает риск lock errors при
  параллельных заявках.
- Docker-образ запускает приложение не от root-пользователя.

## Local checks

```bash
python3 -m compileall backend
node --check script.js
python3 -m json.tool catalog.json
```
