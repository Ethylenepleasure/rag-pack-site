from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from aiohttp import web
from aiogram import Bot

from .catalog import Catalog
from .config import Config
from .notifications import notify_admins
from .storage import Order
from .storage import OrderStorage


REQUIRED_FIELDS = ("product_slug", "customer_name", "delivery_address", "telegram_contact")
FIELD_LIMITS = {
    "product_slug": 80,
    "customer_name": 120,
    "delivery_address": 800,
    "telegram_contact": 120,
}
JSON_CONTENT_TYPE = "application/json"


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
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Vary": "Origin",
    }

    if allow_origin:
        headers["Access-Control-Allow-Origin"] = allow_origin

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


def _rate_limit_middleware(config: Config) -> web.middleware:
    requests_by_ip: dict[str, deque[float]] = defaultdict(deque)

    @web.middleware
    async def middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        if request.method != "POST" or request.path != "/api/orders":
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
    app.cleanup_ctx.append(_notification_context)

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True}, headers=_cors_headers(config, request))

    async def options(request: web.Request) -> web.Response:
        return web.Response(headers=_cors_headers(config, request))

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

        order = storage.create_order(
            source="site",
            product_slug=product.slug,
            product_name=product.name,
            product_price=product.price,
            customer_name=clean_payload["customer_name"],
            delivery_address=clean_payload["delivery_address"],
            telegram_contact=clean_payload["telegram_contact"],
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

    app.router.add_get("/health", health)
    app.router.add_options("/api/orders", options)
    app.router.add_post("/api/orders", create_order)
    return app
