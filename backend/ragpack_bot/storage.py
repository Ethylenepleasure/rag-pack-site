from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


STATUS_NEW = "new"
STATUSES = {
    STATUS_NEW: "Новая",
    "in_progress": "В работе",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
}


@dataclass(frozen=True)
class Order:
    id: int
    source: str
    product_slug: str
    product_name: str
    product_price: str
    customer_name: str
    delivery_address: str
    telegram_contact: str
    status: str
    created_at: str


class OrderStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def init(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    product_slug TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    product_price TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    delivery_address TEXT NOT NULL,
                    telegram_contact TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_order(
        self,
        *,
        source: str,
        product_slug: str,
        product_name: str,
        product_price: str,
        customer_name: str,
        delivery_address: str,
        telegram_contact: str,
    ) -> Order:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    source,
                    product_slug,
                    product_name,
                    product_price,
                    customer_name,
                    delivery_address,
                    telegram_contact,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    product_slug,
                    product_name,
                    product_price,
                    customer_name,
                    delivery_address,
                    telegram_contact,
                    STATUS_NEW,
                    created_at,
                ),
            )

            order_id = int(cursor.lastrowid)

        return self.get_order(order_id)

    def get_order(self, order_id: int) -> Order:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

        if row is None:
            raise KeyError(f"Order {order_id} not found")

        return Order(**dict(row))

    def update_status(self, order_id: int, status: str) -> Order:
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status}")

        with self._connect() as connection:
            connection.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))

        return self.get_order(order_id)
