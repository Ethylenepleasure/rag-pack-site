from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from aiohttp import web
from aiogram import Bot

from .catalog import Catalog
from .config import Config
from .notifications import notify_admins
from .storage import Order, OrderStorage, STATUSES, User


REQUIRED_FIELDS = ("product_slug", "customer_name", "delivery_address", "telegram_contact")
FIELD_LIMITS = {
    "product_slug": 80,
    "customer_name": 120,
    "delivery_address": 800,
    "telegram_contact": 120,
}
JSON_CONTENT_TYPE = "application/json"
SESSION_COOKIE = "ragpack_session"
LOGIN_CODE_LIMIT = 6


def _static_root(config: Config) -> Path:
    catalog_root = config.catalog_path.parent

    if (catalog_root / "index.html").exists():
        return catalog_root

    return Path.cwd()


def _cors_headers(config: Config, request: web.Request) -> dict[str, str]:
    origin = request.headers.get("Origin", "")
    allowed = config.cors_origins

    if "*" in allowed:
        allow_origin = "*"
    elif origin in allowed:
        allow_origin = origin
    else:
        allow_origin = ""

    headers = {
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
        "Vary": "Origin",
    }

    if allow_origin:
        headers["Access-Control-Allow-Origin"] = allow_origin
        if allow_origin != "*":
            headers["Access-Control-Allow-Credentials"] = "true"

    return headers


def _client_ip(request: web.Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    peername = request.transport.get_extra_info("peername") if request.transport else None
    return str(peername[0]) if peername else "unknown"


def _trim_payload(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None

    result: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = payload.get(field)

        if not isinstance(value, str):
            return None

        value = value.strip()
        if not value or len(value) > FIELD_LIMITS[field]:
            return None

        result[field] = value

    return result


async def _json_payload(request: web.Request) -> object | None:
    if not request.content_type.startswith(JSON_CONTENT_TYPE):
        return None

    try:
        return await request.json()
    except (ValueError, web.HTTPRequestEntityTooLarge):
        return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_token(request: web.Request) -> str:
    return request.cookies.get(SESSION_COOKIE, "")


def _current_user(request: web.Request) -> User | None:
    storage: OrderStorage = request.app["storage"]
    token = _session_token(request)

    if not token:
        return None

    return storage.get_user_by_session(_hash_token(token))


def _user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _order_payload(order: Order) -> dict[str, object]:
    return asdict(order)


def _login_url(config: Config) -> str:
    separator = "&" if "?" in config.bot_url else "?"
    return f"{config.bot_url}{separator}start=login"


def _auth_error(config: Config, request: web.Request, *, admin: bool = False) -> web.Response:
    return web.json_response(
        {"detail": "Forbidden" if admin else "Authentication required"},
        status=403 if admin else 401,
        headers=_cors_headers(config, request),
    )


def _rate_limit_middleware(config: Config) -> web.middleware:
    requests_by_ip: dict[str, deque[float]] = defaultdict(deque)

    @web.middleware
    async def middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        if request.method != "POST" or request.path not in {"/api/orders", "/api/auth/verify"}:
            return await handler(request)

        now = time.monotonic()
        cutoff = now - config.rate_limit_window_seconds
        timestamps = requests_by_ip[_client_ip(request)]

        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= config.rate_limit_requests:
            return web.json_response(
                {"detail": "Too many requests"},
                status=429,
                headers=_cors_headers(config, request),
            )

        timestamps.append(now)
        return await handler(request)

    return middleware


async def _notification_worker(app: web.Application) -> None:
    config: Config = app["config"]
    bot: Bot = app["bot"]
    queue: asyncio.Queue[Order | None] = app["notification_queue"]

    while True:
        order = await queue.get()

        try:
            if order is None:
                return

            await notify_admins(bot, config, order)
        finally:
            queue.task_done()


async def _notification_context(app: web.Application):
    queue: asyncio.Queue[Order | None] = asyncio.Queue(maxsize=app["config"].notification_queue_size)
    app["notification_queue"] = queue
    worker = asyncio.create_task(_notification_worker(app))

    try:
        yield
    finally:
        await queue.put(None)
        await worker


def create_app(config: Config, bot: Bot, catalog: Catalog, storage: OrderStorage) -> web.Application:
    app = web.Application(
        client_max_size=config.max_request_size,
        middlewares=[_rate_limit_middleware(config)],
    )
    app["config"] = config
    app["bot"] = bot
    app["catalog"] = catalog
    app["storage"] = storage
    app["static_root"] = _static_root(config)
    app.cleanup_ctx.append(_notification_context)

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True}, headers=_cors_headers(config, request))

    async def options(request: web.Request) -> web.Response:
        return web.Response(headers=_cors_headers(config, request))

    async def static_page(request: web.Request) -> web.FileResponse:
        page = "index.html"
        if request.path == "/profile":
            page = "profile.html"
        elif request.path == "/admin":
            page = "admin.html"

        return web.FileResponse(request.app["static_root"] / page)

    async def static_file(request: web.Request) -> web.FileResponse:
        return web.FileResponse(request.app["static_root"] / request.match_info["filename"])

    async def start_auth(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "bot_url": config.bot_url,
                "login_url": _login_url(config),
                "detail": "Open the Telegram bot and request a login code.",
            },
            headers=_cors_headers(config, request),
        )

    async def verify_auth(request: web.Request) -> web.Response:
        payload = await _json_payload(request)

        if not isinstance(payload, dict):
            return web.json_response(
                {"detail": "Invalid JSON"},
                status=400,
                headers=_cors_headers(config, request),
            )

        code = str(payload.get("code", "")).strip()
        if not code.isdigit() or len(code) != LOGIN_CODE_LIMIT:
            return web.json_response(
                {"detail": "Invalid code"},
                status=422,
                headers=_cors_headers(config, request),
            )

        user = storage.consume_login_code(code)
        if user is None:
            return web.json_response(
                {"detail": "Code is invalid or expired"},
                status=401,
                headers=_cors_headers(config, request),
            )

        token = secrets.token_urlsafe(32)
        storage.create_session(user_id=user.id, token_hash=_hash_token(token), ttl_days=30)
        response = web.json_response(
            {"ok": True, "user": _user_payload(user)},
            headers=_cors_headers(config, request),
        )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            secure=config.secure_cookies,
            samesite="Lax",
            path="/",
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        token = _session_token(request)
        if token:
            storage.delete_session(_hash_token(token))

        response = web.json_response({"ok": True}, headers=_cors_headers(config, request))
        response.del_cookie(SESSION_COOKIE, path="/")
        return response

    async def profile(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None:
            return _auth_error(config, request)

        orders = storage.list_orders(user_id=user.id)
        return web.json_response(
            {
                "user": _user_payload(user),
                "orders": [_order_payload(order) for order in orders],
                "statuses": STATUSES,
            },
            headers=_cors_headers(config, request),
        )

    async def admin_orders(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not user.is_admin:
            return _auth_error(config, request, admin=user is not None)

        status = request.query.get("status", "").strip()
        if status and status not in STATUSES:
            return web.json_response(
                {"detail": "Unknown status"},
                status=422,
                headers=_cors_headers(config, request),
            )

        orders = storage.list_orders(status=status or None)
        return web.json_response(
            {
                "orders": [_order_payload(order) for order in orders],
                "statuses": STATUSES,
            },
            headers=_cors_headers(config, request),
        )

    async def update_admin_order(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not user.is_admin:
            return _auth_error(config, request, admin=user is not None)

        payload = await _json_payload(request)
        if not isinstance(payload, dict):
            return web.json_response(
                {"detail": "Invalid JSON"},
                status=400,
                headers=_cors_headers(config, request),
            )

        status = str(payload.get("status", "")).strip()
        if status not in STATUSES:
            return web.json_response(
                {"detail": "Unknown status"},
                status=422,
                headers=_cors_headers(config, request),
            )

        try:
            order = storage.update_status(int(request.match_info["order_id"]), status)
        except (KeyError, ValueError):
            return web.json_response(
                {"detail": "Order not found"},
                status=404,
                headers=_cors_headers(config, request),
            )

        return web.json_response(
            {"ok": True, "order": _order_payload(order)},
            headers=_cors_headers(config, request),
        )

    async def admin_customers(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not user.is_admin:
            return _auth_error(config, request, admin=user is not None)

        customers = []
        for customer in storage.list_users():
            note = storage.get_customer_note(customer.id)
            orders = storage.list_orders(user_id=customer.id)
            customers.append(
                {
                    "user": _user_payload(customer),
                    "note": note.note if note else "",
                    "orders_count": len(orders),
                    "last_order": _order_payload(orders[0]) if orders else None,
                }
            )

        return web.json_response({"customers": customers}, headers=_cors_headers(config, request))

    async def update_customer_note(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not user.is_admin:
            return _auth_error(config, request, admin=user is not None)

        payload = await _json_payload(request)
        if not isinstance(payload, dict):
            return web.json_response(
                {"detail": "Invalid JSON"},
                status=400,
                headers=_cors_headers(config, request),
            )

        note = str(payload.get("note", "")).strip()
        if len(note) > 1000:
            return web.json_response(
                {"detail": "Note is too long"},
                status=422,
                headers=_cors_headers(config, request),
            )

        try:
            customer_id = int(request.match_info["customer_id"])
            storage.get_user(customer_id)
        except (KeyError, ValueError):
            return web.json_response(
                {"detail": "Customer not found"},
                status=404,
                headers=_cors_headers(config, request),
            )

        customer_note = storage.set_customer_note(customer_id, note)
        return web.json_response(
            {"ok": True, "note": asdict(customer_note)},
            headers=_cors_headers(config, request),
        )

    async def create_order(request: web.Request) -> web.Response:
        if not request.content_type.startswith(JSON_CONTENT_TYPE):
            return web.json_response(
                {"detail": "Content-Type must be application/json"},
                status=415,
                headers=_cors_headers(config, request),
            )

        try:
            payload = await request.json()
        except (ValueError, web.HTTPRequestEntityTooLarge):
            return web.json_response(
                {"detail": "Invalid JSON"},
                status=400,
                headers=_cors_headers(config, request),
            )

        clean_payload = _trim_payload(payload)
        if clean_payload is None:
            return web.json_response(
                {"detail": "Invalid order fields"},
                status=422,
                headers=_cors_headers(config, request),
            )

        product = catalog.get(clean_payload["product_slug"])

        if product is None:
            return web.json_response(
                {"detail": "Unknown product"},
                status=422,
                headers=_cors_headers(config, request),
            )

        user = _current_user(request)
        order = storage.create_order(
            source="site",
            product_slug=product.slug,
            product_name=product.name,
            product_price=product.price,
            customer_name=clean_payload["customer_name"],
            delivery_address=clean_payload["delivery_address"],
            telegram_contact=clean_payload["telegram_contact"],
            user_id=user.id if user else None,
        )

        try:
            app["notification_queue"].put_nowait(order)
        except asyncio.QueueFull:
            await notify_admins(bot, config, order)

        return web.json_response(
            {"ok": True, "order_id": order.id},
            status=201,
            headers=_cors_headers(config, request),
        )

    app.router.add_get("/", static_page)
    app.router.add_get("/profile", static_page)
    app.router.add_get("/admin", static_page)
    app.router.add_static("/assets", app["static_root"] / "assets")
    app.router.add_get("/{filename:styles\\.css|script\\.js|profile\\.js|admin\\.js|catalog\\.json}", static_file)
    app.router.add_get("/health", health)
    app.router.add_options("/{tail:.*}", options)
    app.router.add_post("/api/auth/start", start_auth)
    app.router.add_post("/api/auth/verify", verify_auth)
    app.router.add_post("/api/auth/logout", logout)
    app.router.add_get("/api/profile", profile)
    app.router.add_get("/api/admin/orders", admin_orders)
    app.router.add_patch("/api/admin/orders/{order_id}", update_admin_order)
    app.router.add_get("/api/admin/customers", admin_customers)
    app.router.add_patch("/api/admin/customers/{customer_id}/note", update_customer_note)
    app.router.add_post("/api/orders", create_order)
    return app
