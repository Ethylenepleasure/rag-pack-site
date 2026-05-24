from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    user_id: int | None
    product_slug: str
    product_name: str
    product_price: str
    customer_name: str
    delivery_address: str
    telegram_contact: str
    status: str
    created_at: str


@dataclass(frozen=True)
class User:
    id: int
    telegram_user_id: int
    telegram_username: str
    phone: str
    first_name: str
    last_name: str
    is_admin: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LoginCode:
    id: int
    user_id: int
    code: str
    expires_at: str
    used_at: str | None
    created_at: str


@dataclass(frozen=True)
class Session:
    id: int
    user_id: int
    token_hash: str
    expires_at: str
    created_at: str


@dataclass(frozen=True)
class CustomerNote:
    user_id: int
    note: str
    updated_at: str


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
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(orders)").fetchall()
            }
            if "user_id" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL UNIQUE,
                    telegram_username TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    first_name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '',
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS login_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_notes (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    note TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_login_codes_code ON login_codes(code)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash)")

    def upsert_user(
        self,
        *,
        telegram_user_id: int,
        telegram_username: str,
        phone: str,
        first_name: str,
        last_name: str,
        is_admin: bool,
    ) -> User:
        now = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()

            if row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id,
                        telegram_username,
                        phone,
                        first_name,
                        last_name,
                        is_admin,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_user_id,
                        telegram_username,
                        phone,
                        first_name,
                        last_name,
                        1 if is_admin else 0,
                        now,
                        now,
                    ),
                )
                user_id = int(cursor.lastrowid)
            else:
                user_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE users
                    SET telegram_username = ?,
                        phone = ?,
                        first_name = ?,
                        last_name = ?,
                        is_admin = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        telegram_username,
                        phone,
                        first_name,
                        last_name,
                        1 if is_admin else 0,
                        now,
                        user_id,
                    ),
                )

            contact_variants = {str(telegram_user_id)}
            if telegram_username:
                contact_variants.update(
                    {
                        telegram_username,
                        f"@{telegram_username}",
                        f"@{telegram_username} / {telegram_user_id}",
                    }
                )
            connection.executemany(
                "UPDATE orders SET user_id = ? WHERE user_id IS NULL AND telegram_contact = ?",
                [(user_id, contact) for contact in contact_variants],
            )

        return self.get_user(user_id)

    def get_user(self, user_id: int) -> User:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        if row is None:
            raise KeyError(f"User {user_id} not found")

        data = dict(row)
        data["is_admin"] = bool(data["is_admin"])
        return User(**data)

    def get_user_by_telegram_id(self, telegram_user_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()

        if row is None:
            return None

        data = dict(row)
        data["is_admin"] = bool(data["is_admin"])
        return User(**data)

    def create_login_code(self, user_id: int, code: str, ttl_minutes: int = 10) -> LoginCode:
        now = datetime.now(UTC)
        created_at = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE login_codes
                SET used_at = ?
                WHERE user_id = ? AND used_at IS NULL
                """,
                (created_at, user_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO login_codes (user_id, code, expires_at, used_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (user_id, code, expires_at, created_at),
            )
            code_id = int(cursor.lastrowid)

        return self.get_login_code(code_id)

    def get_login_code(self, code_id: int) -> LoginCode:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM login_codes WHERE id = ?", (code_id,)).fetchone()

        if row is None:
            raise KeyError(f"Login code {code_id} not found")

        return LoginCode(**dict(row))

    def consume_login_code(self, code: str) -> User | None:
        now = datetime.now(UTC)
        now_raw = now.isoformat(timespec="seconds")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM login_codes
                WHERE code = ? AND used_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()

            if row is None:
                return None

            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at <= now:
                return None

            connection.execute("UPDATE login_codes SET used_at = ? WHERE id = ?", (now_raw, row["id"]))
            user_id = int(row["user_id"])

        return self.get_user(user_id)

    def create_session(self, *, user_id: int, token_hash: str, ttl_days: int = 30) -> Session:
        now = datetime.now(UTC)
        created_at = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(days=ttl_days)).isoformat(timespec="seconds")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sessions (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, token_hash, expires_at, created_at),
            )
            session_id = int(cursor.lastrowid)

        return Session(session_id, user_id, token_hash, expires_at, created_at)

    def get_user_by_session(self, token_hash: str) -> User | None:
        now = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()

        if row is None:
            return None

        data = dict(row)
        data["is_admin"] = bool(data["is_admin"])
        return User(**data)

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def list_orders(self, *, status: str | None = None, user_id: int | None = None) -> list[Order]:
        where: list[str] = []
        values: list[object] = []

        if status:
            where.append("status = ?")
            values.append(status)

        if user_id is not None:
            where.append("user_id = ?")
            values.append(user_id)

        query = "SELECT * FROM orders"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC"

        with self._connect() as connection:
            rows = connection.execute(query, tuple(values)).fetchall()

        return [Order(**dict(row)) for row in rows]

    def list_users(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY updated_at DESC, id DESC").fetchall()

        users = []
        for row in rows:
            data = dict(row)
            data["is_admin"] = bool(data["is_admin"])
            users.append(User(**data))

        return users

    def get_customer_note(self, user_id: int) -> CustomerNote | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM customer_notes WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        return CustomerNote(**dict(row)) if row is not None else None

    def set_customer_note(self, user_id: int, note: str) -> CustomerNote:
        updated_at = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_notes (user_id, note, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (user_id, note, updated_at),
            )

        return CustomerNote(user_id=user_id, note=note, updated_at=updated_at)

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
        user_id: int | None = None,
    ) -> Order:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    source,
                    user_id,
                    product_slug,
                    product_name,
                    product_price,
                    customer_name,
                    delivery_address,
                    telegram_contact,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    user_id,
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
