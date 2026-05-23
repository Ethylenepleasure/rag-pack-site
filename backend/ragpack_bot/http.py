from __future__ import annotations

from aiohttp import web
from aiogram import Bot

from .catalog import Catalog
from .config import Config
from .notifications import notify_admins
from .storage import OrderStorage


REQUIRED_FIELDS = ("product_slug", "customer_name", "delivery_address", "telegram_contact")


def _cors_headers(config: Config, request: web.Request) -> dict[str, str]:
    origin = request.headers.get("Origin", "")
    allowed = config.cors_origins

    if "*" in allowed:
        allow_origin = "*"
    elif origin in allowed:
        allow_origin = origin
    else:
        allow_origin = allowed[0]

    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }


def create_app(config: Config, bot: Bot, catalog: Catalog, storage: OrderStorage) -> web.Application:
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True}, headers=_cors_headers(config, request))

    async def options(request: web.Request) -> web.Response:
        return web.Response(headers=_cors_headers(config, request))

    async def create_order(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response(
                {"detail": "Invalid JSON"},
                status=400,
                headers=_cors_headers(config, request),
            )

        missing = [field for field in REQUIRED_FIELDS if not str(payload.get(field, "")).strip()]

        if missing:
            return web.json_response(
                {"detail": f"Missing fields: {', '.join(missing)}"},
                status=422,
                headers=_cors_headers(config, request),
            )

        product = catalog.get(str(payload["product_slug"]).strip())

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
            customer_name=str(payload["customer_name"]).strip(),
            delivery_address=str(payload["delivery_address"]).strip(),
            telegram_contact=str(payload["telegram_contact"]).strip(),
        )
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
