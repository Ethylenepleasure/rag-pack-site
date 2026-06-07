from __future__ import annotations

import asyncio
import hashlib
import html
import re
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from aiohttp import web
from aiogram import Bot

from .catalog import Catalog, Product, RuntimeCatalog
from .config import Config
from .notifications import notify_admins
from .storage import Order, OrderStorage, STATUSES, User


REQUIRED_FIELDS = ("product_slug", "customer_name", "delivery_address")
REQUIRED_PRODUCT_FIELDS = ("slug", "category", "tag", "name", "description", "price", "image", "alt")
PRODUCT_FIELD_LIMITS = {
    "slug": 80,
    "category": 40,
    "tag": 80,
    "name": 120,
    "description": 400,
    "price": 80,
    "image": 240,
    "alt": 240,
    "display_name": 160,
    "title_mark": 40,
    "title_size": 40,
    "image_fit": 40,
    "detail_description": 1200,
    "notes": 600,
}
FIELD_LIMITS = {
    "product_slug": 80,
    "customer_name": 120,
    "delivery_address": 800,
    "telegram_contact": 120,
}
JSON_CONTENT_TYPE = "application/json"
SESSION_COOKIE = "ragpack_session"
LOGIN_CODE_LIMIT = 6
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UPLOAD_CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
PUBLIC_SITE_ORIGIN = "https://ragpack.ru"
NOINDEX_HEADER = "noindex, nofollow, noarchive"


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
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
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


def _trim_field(payload: dict[str, object], field: str) -> str | None:
    value = payload.get(field)

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value or len(value) > FIELD_LIMITS[field]:
        return None

    return value


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


def _is_admin(config: Config, user: User) -> bool:
    return user.telegram_user_id in config.admin_ids


def _user_payload(config: Config, user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_admin": _is_admin(config, user),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _telegram_contact(user: User) -> str:
    if user.telegram_username:
        return f"@{user.telegram_username}"

    return str(user.telegram_user_id)


def _order_payload(order: Order) -> dict[str, object]:
    return asdict(order)


def _product_payload(product: Product) -> dict[str, object]:
    return product.to_dict()


def _html(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _product_title(product: Product) -> str:
    return f"{product.name} / RĄG PACK//"


def _product_description(product: Product) -> str:
    return product.detail_description or product.description


def _public_product_url(product: Product) -> str:
    return f"{PUBLIC_SITE_ORIGIN}/product/{product.slug}"


def _public_asset_url(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{PUBLIC_SITE_ORIGIN}/{path.lstrip('/')}"


def _display_product_name(product: Product) -> str:
    return (product.display_name or product.name).replace("\n", " ")


def _render_product_page(product: Product, static_root: Path) -> web.Response:
    title = _product_title(product)
    description = _product_description(product)
    canonical_url = _public_product_url(product)
    image_url = _public_asset_url(product.image)
    template = (static_root / "product.html").read_text(encoding="utf-8")

    template = re.sub(r"<title>.*?</title>", f"<title>{_html(title)}</title>", template, count=1, flags=re.S)
    replacements = {
        r'<meta name="description" content="[^"]*" />': f'<meta name="description" content="{_html(description)}" />',
        r'<meta property="og:title" content="[^"]*" />': f'<meta property="og:title" content="{_html(title)}" />',
        r'<meta property="og:description" content="[^"]*" />': f'<meta property="og:description" content="{_html(description)}" />',
        r'<meta property="og:image" content="[^"]*" />': f'<meta property="og:image" content="{_html(image_url)}" />',
        r'<meta property="og:url" content="[^"]*" />': f'<meta property="og:url" content="{_html(canonical_url)}" />',
        r'<link rel="canonical" href="[^"]*" />': f'<link rel="canonical" href="{_html(canonical_url)}" />',
    }
    for pattern, replacement in replacements.items():
        template = re.sub(pattern, replacement, template, count=1)

    content = f"""
    <section class="product-detail__state product-detail__state--seo">
      <p class="section-label">{_html(product.tag or product.category)}</p>
      <h1>{_html(_display_product_name(product))}</h1>
      <p>{_html(description)}</p>
      <a class="hero__button" href="https://ragpack.ru/#catalog">Вернуться в каталог</a>
    </section>
    """
    template = re.sub(
        r'<main class="product-detail" id="product-detail" aria-live="polite">.*?</main>',
        f'<main class="product-detail" id="product-detail" aria-live="polite">{content}</main>',
        template,
        count=1,
        flags=re.S,
    )
    return web.Response(text=template, content_type="text/html")


def _sitemap_xml(products: list[Product]) -> str:
    urls = [f"{PUBLIC_SITE_ORIGIN}/", *[_public_product_url(product) for product in products]]
    items = "\n".join(
        f"  <url><loc>{_html(url)}</loc><changefreq>weekly</changefreq></url>"
        for url in urls
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'


def _login_url(config: Config) -> str:
    separator = "&" if "?" in config.bot_url else "?"
    return f"{config.bot_url}{separator}start=login"


def _auth_error(config: Config, request: web.Request, *, admin: bool = False) -> web.Response:
    return web.json_response(
        {"detail": "Forbidden" if admin else "Authentication required"},
        status=403 if admin else 401,
        headers=_cors_headers(config, request),
    )


def _clean_product_text(payload: dict[str, object], field: str, *, required: bool = False) -> str | None:
    value = payload.get(field, "")

    if not isinstance(value, str):
        return None

    value = value.strip()
    if required and not value:
        return None

    limit = PRODUCT_FIELD_LIMITS[field]
    if len(value) > limit:
        return None

    return value


def _clean_gallery(value: object) -> list[dict[str, str]] | None:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        return None

    gallery: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        image = str(item.get("image", "")).strip()
        alt = str(item.get("alt", "")).strip()
        if not image:
            continue
        if len(image) > PRODUCT_FIELD_LIMITS["image"] or len(alt) > PRODUCT_FIELD_LIMITS["alt"]:
            return None
        gallery.append({"image": image, "alt": alt})

    return gallery


def _clean_features(value: object) -> list[str] | None:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 12:
        return None

    features = [str(item).strip() for item in value if str(item).strip()]
    if any(len(item) > 240 for item in features):
        return None
    return features


def _clean_specs(value: object) -> dict[str, str] | None:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 12:
        return None

    specs: dict[str, str] = {}
    for key, item in value.items():
        label = str(key).strip()
        text = str(item).strip()
        if not label or not text:
            continue
        if len(label) > 80 or len(text) > 240:
            return None
        specs[label] = text
    return specs


def _clean_bool(value: object) -> bool:
    return bool(value)


def _clean_product(payload: object, *, existing: Product | None = None) -> Product | None:
    if not isinstance(payload, dict):
        return None

    strings: dict[str, str] = {}
    for field in PRODUCT_FIELD_LIMITS:
        required = field in REQUIRED_PRODUCT_FIELDS
        value = _clean_product_text(payload, field, required=required)
        if value is None:
            return None
        strings[field] = value

    if not SLUG_PATTERN.fullmatch(strings["slug"]):
        return None

    gallery = _clean_gallery(payload.get("gallery"))
    features = _clean_features(payload.get("features"))
    specs = _clean_specs(payload.get("specs"))
    if gallery is None or features is None or specs is None:
        return None

    return Product(
        slug=strings["slug"],
        category=strings["category"],
        tag=strings["tag"],
        name=strings["name"],
        description=strings["description"],
        price=strings["price"],
        image=strings["image"],
        alt=strings["alt"],
        display_name=strings["display_name"],
        title_mark=strings["title_mark"],
        title_size=strings["title_size"],
        image_fit=strings["image_fit"] or "cover",
        detail_description=strings["detail_description"],
        gallery=gallery,
        features=features,
        specs=specs,
        notes=strings["notes"],
        is_published=_clean_bool(payload.get("is_published", existing.is_published if existing else False)),
        is_archived=_clean_bool(payload.get("is_archived", existing.is_archived if existing else False)),
        created_at=existing.created_at if existing else "",
        updated_at=existing.updated_at if existing else "",
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


def _robots_header_middleware() -> web.middleware:
    @web.middleware
    async def middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        response = await handler(request)
        if request.path.startswith("/api/") or request.path in {"/profile", "/profile.html", "/admin", "/admin.html"}:
            response.headers["X-Robots-Tag"] = NOINDEX_HEADER
        return response

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


def create_app(config: Config, bot: Bot, catalog: Catalog | RuntimeCatalog, storage: OrderStorage) -> web.Application:
    app = web.Application(
        client_max_size=config.max_request_size,
        middlewares=[_rate_limit_middleware(config), _robots_header_middleware()],
    )
    app["config"] = config
    app["bot"] = bot
    app["catalog"] = catalog
    app["storage"] = storage
    app["static_root"] = _static_root(config)
    config.uploads_path.mkdir(parents=True, exist_ok=True)
    app.cleanup_ctx.append(_notification_context)

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True}, headers=_cors_headers(config, request))

    async def public_catalog(request: web.Request) -> web.Response:
        products = storage.list_products(public_only=True)
        return web.json_response([_product_payload(product) for product in products], headers=_cors_headers(config, request))

    async def options(request: web.Request) -> web.Response:
        return web.Response(headers=_cors_headers(config, request))

    async def robots_txt(request: web.Request) -> web.Response:
        text = "\n".join(
            [
                "User-agent: *",
                "Disallow: /profile",
                "Disallow: /profile.html",
                "Disallow: /admin",
                "Disallow: /admin.html",
                "Disallow: /api/",
                f"Sitemap: {PUBLIC_SITE_ORIGIN}/sitemap.xml",
                "",
            ]
        )
        return web.Response(text=text, content_type="text/plain")

    async def sitemap_xml(request: web.Request) -> web.Response:
        products = storage.list_products(public_only=True)
        return web.Response(text=_sitemap_xml(products), content_type="application/xml")

    async def static_page(request: web.Request) -> web.FileResponse:
        if request.host.split(":", 1)[0] == "api.ragpack.ru" and request.path in {"/", "/index.html"}:
            raise web.HTTPFound("https://ragpack.ru/")

        if request.path == "/product.html":
            slug = request.query.get("slug", "")
            if slug and SLUG_PATTERN.fullmatch(slug):
                raise web.HTTPMovedPermanently(location=f"/product/{slug}")

        page = "index.html"
        if request.path in {"/profile", "/profile.html", "/admin", "/admin.html"}:
            page = "profile.html"
        elif request.path.startswith("/product/"):
            product = storage.get_product(request.match_info["slug"], public_only=True)
            if product is None:
                return web.Response(text="Product not found", status=404, headers={"X-Robots-Tag": NOINDEX_HEADER})
            return _render_product_page(product, request.app["static_root"])
        elif request.path == "/product.html":
            page = "product.html"

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
            {"ok": True, "user": _user_payload(config, user)},
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
                "user": _user_payload(config, user),
                "orders": [_order_payload(order) for order in orders],
                "statuses": STATUSES,
            },
            headers=_cors_headers(config, request),
        )

    async def admin_orders(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
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
        if user is None or not _is_admin(config, user):
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
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        customers = []
        for customer in storage.list_users():
            note = storage.get_customer_note(customer.id)
            orders = storage.list_orders(user_id=customer.id)
            customers.append(
                {
                    "user": _user_payload(config, customer),
                    "note": note.note if note else "",
                    "orders_count": len(orders),
                    "last_order": _order_payload(orders[0]) if orders else None,
                }
            )

        return web.json_response({"customers": customers}, headers=_cors_headers(config, request))

    async def admin_products(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        products = storage.list_products(public_only=False)
        return web.json_response({"products": [_product_payload(product) for product in products]}, headers=_cors_headers(config, request))

    async def create_admin_product(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        payload = await _json_payload(request)
        product = _clean_product(payload)
        if product is None:
            return web.json_response({"detail": "Invalid product fields"}, status=422, headers=_cors_headers(config, request))

        if storage.get_product(product.slug) is not None:
            return web.json_response({"detail": "Product slug already exists"}, status=409, headers=_cors_headers(config, request))

        saved = storage.save_product(product)
        return web.json_response({"ok": True, "product": _product_payload(saved)}, status=201, headers=_cors_headers(config, request))

    async def update_admin_product(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        current_slug = request.match_info["slug"]
        existing = storage.get_product(current_slug)
        if existing is None:
            return web.json_response({"detail": "Product not found"}, status=404, headers=_cors_headers(config, request))

        payload = await _json_payload(request)
        product = _clean_product(payload, existing=existing)
        if product is None:
            return web.json_response({"detail": "Invalid product fields"}, status=422, headers=_cors_headers(config, request))

        try:
            saved = storage.save_product(product, previous_slug=current_slug)
        except ValueError:
            return web.json_response({"detail": "Product slug already exists"}, status=409, headers=_cors_headers(config, request))

        return web.json_response({"ok": True, "product": _product_payload(saved)}, headers=_cors_headers(config, request))

    async def archive_admin_product(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        try:
            product = storage.archive_product(request.match_info["slug"])
        except KeyError:
            return web.json_response({"detail": "Product not found"}, status=404, headers=_cors_headers(config, request))

        return web.json_response({"ok": True, "product": _product_payload(product)}, headers=_cors_headers(config, request))

    async def upload_admin_file(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
            return _auth_error(config, request, admin=user is not None)

        if not request.content_type.startswith("multipart/form-data"):
            return web.json_response({"detail": "Content-Type must be multipart/form-data"}, status=415, headers=_cors_headers(config, request))

        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "file" or not field.filename:
            return web.json_response({"detail": "Missing upload file"}, status=422, headers=_cors_headers(config, request))

        suffix = UPLOAD_CONTENT_TYPES.get(field.headers.get("Content-Type", "").split(";", 1)[0].strip().lower())
        if suffix is None:
            return web.json_response({"detail": "Unsupported image type"}, status=422, headers=_cors_headers(config, request))

        filename = f"{int(time.time())}-{secrets.token_urlsafe(8)}{suffix}"
        upload_path = config.uploads_path / filename
        size = 0
        with upload_path.open("wb") as file:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > config.max_request_size:
                    upload_path.unlink(missing_ok=True)
                    return web.json_response({"detail": "Upload is too large"}, status=413, headers=_cors_headers(config, request))
                file.write(chunk)

        return web.json_response({"ok": True, "path": f"/uploads/{filename}"}, status=201, headers=_cors_headers(config, request))

    async def update_customer_note(request: web.Request) -> web.Response:
        user = _current_user(request)
        if user is None or not _is_admin(config, user):
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
        telegram_contact = _telegram_contact(user) if user else _trim_field(payload, "telegram_contact")

        if telegram_contact is None:
            return web.json_response(
                {"detail": "Invalid order fields"},
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
            telegram_contact=telegram_contact,
            telegram_user_id=user.telegram_user_id if user else None,
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

    for page_path in ("/", "/index.html", "/profile", "/profile.html", "/admin", "/admin.html", "/product.html"):
        app.router.add_get(page_path, static_page)
        app.router.add_post(page_path, static_page)
    app.router.add_get("/robots.txt", robots_txt)
    app.router.add_get("/sitemap.xml", sitemap_xml)
    app.router.add_static("/assets", app["static_root"] / "assets")
    app.router.add_static("/uploads", config.uploads_path)
    app.router.add_get(
        "/{filename:styles\\.css|shared\\.js|script\\.js|product\\.js|profile\\.js|admin\\.js|catalog\\.json}",
        static_file,
    )
    app.router.add_get("/product/{slug}", static_page)
    app.router.add_get("/health", health)
    app.router.add_get("/api/catalog", public_catalog)
    app.router.add_options("/{tail:.*}", options)
    app.router.add_post("/api/auth/start", start_auth)
    app.router.add_post("/api/auth/verify", verify_auth)
    app.router.add_post("/api/auth/logout", logout)
    app.router.add_get("/api/profile", profile)
    app.router.add_get("/api/admin/orders", admin_orders)
    app.router.add_patch("/api/admin/orders/{order_id}", update_admin_order)
    app.router.add_get("/api/admin/customers", admin_customers)
    app.router.add_patch("/api/admin/customers/{customer_id}/note", update_customer_note)
    app.router.add_get("/api/admin/products", admin_products)
    app.router.add_post("/api/admin/products", create_admin_product)
    app.router.add_patch("/api/admin/products/{slug}", update_admin_product)
    app.router.add_delete("/api/admin/products/{slug}", archive_admin_product)
    app.router.add_post("/api/admin/uploads", upload_admin_file)
    app.router.add_post("/api/orders", create_order)
    return app
