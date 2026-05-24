from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    database_path: Path
    catalog_path: Path
    host: str
    port: int
    cors_origins: tuple[str, ...]
    max_request_size: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    notification_queue_size: int


def _parse_admin_ids(value: str) -> tuple[int, ...]:
    admin_ids: list[int] = []

    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        admin_ids.append(int(item))

    return tuple(admin_ids)


def _parse_origins(value: str) -> tuple[str, ...]:
    origins = tuple(origin.strip() for origin in value.split(",") if origin.strip())

    if not origins:
        raise RuntimeError("CORS_ORIGINS is required")

    return origins


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is required")

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        database_path=Path(os.getenv("DATABASE_PATH", "/data/orders.sqlite3")),
        catalog_path=Path(os.getenv("CATALOG_PATH", "/app/catalog.json")),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        cors_origins=_parse_origins(os.getenv("CORS_ORIGINS", "")),
        max_request_size=int(os.getenv("MAX_REQUEST_SIZE", "8192")),
        rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "10")),
        rate_limit_window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        notification_queue_size=int(os.getenv("NOTIFICATION_QUEUE_SIZE", "100")),
    )
