from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Config
from .storage import Order, STATUSES


def format_order(order: Order) -> str:
    status = STATUSES.get(order.status, order.status)

    return "\n".join(
        (
            f"<b>Заявка #{order.id}</b>",
            f"Статус: <b>{escape(status)}</b>",
            f"Источник: <b>{escape(order.source)}</b>",
            "",
            f"Товар: <b>{escape(order.product_name)}</b>",
            f"Цена: {escape(order.product_price)}",
            "",
            f"Имя: {escape(order.customer_name)}",
            f"Адрес доставки: {escape(order.delivery_address)}",
            f"Telegram: {escape(order.telegram_contact)}",
            "",
            f"Создана: {escape(order.created_at)}",
        )
    )


def status_keyboard(order_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"status:{order_id}:{status}")
        for status, label in STATUSES.items()
    ]

    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]])


async def notify_admins(bot: Bot, config: Config, order: Order) -> None:
    for admin_id in config.admin_ids:
        await bot.send_message(
            chat_id=admin_id,
            text=format_order(order),
            reply_markup=status_keyboard(order.id),
        )
