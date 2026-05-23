from __future__ import annotations

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .catalog import Catalog, Product
from .config import Config
from .notifications import format_order, notify_admins, status_keyboard
from .storage import OrderStorage, STATUSES


class OrderForm(StatesGroup):
    product_slug = State()
    customer_name = State()
    delivery_address = State()


def _product_keyboard(catalog: Catalog) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{product.name} / {product.price}", callback_data=f"order:{product.slug}")]
        for product in catalog.products
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _telegram_contact(message: Message) -> str:
    user = message.from_user

    if user is None:
        return "unknown"

    if user.username:
        return f"@{user.username} / {user.id}"

    return str(user.id)


def _product_line(product: Product) -> str:
    return f"{product.name} / {product.price}"


def create_dispatcher(config: Config, catalog: Catalog, storage: OrderStorage) -> Dispatcher:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        parts = (message.text or "").split(maxsplit=1)
        slug = parts[1].strip() if len(parts) > 1 else ""
        product = catalog.get(slug) if slug else None

        if product is not None:
            await state.set_state(OrderForm.customer_name)
            await state.update_data(product_slug=product.slug)
            await message.answer(f"Оформляем заказ: {_product_line(product)}\n\nКак вас зовут?")
            return

        await message.answer(
            "Выберите товар для заказа:",
            reply_markup=_product_keyboard(catalog),
        )

    @router.callback_query(F.data.startswith("order:"))
    async def pick_product(callback: CallbackQuery, state: FSMContext) -> None:
        slug = callback.data.split(":", 1)[1] if callback.data else ""
        product = catalog.get(slug)

        if product is None:
            await callback.answer("Товар не найден", show_alert=True)
            return

        await state.set_state(OrderForm.customer_name)
        await state.update_data(product_slug=product.slug)
        await callback.message.answer(f"Оформляем заказ: {_product_line(product)}\n\nКак вас зовут?")
        await callback.answer()

    @router.message(OrderForm.customer_name)
    async def collect_name(message: Message, state: FSMContext) -> None:
        customer_name = (message.text or "").strip()

        if not customer_name:
            await message.answer("Напишите имя текстом.")
            return

        await state.update_data(customer_name=customer_name)
        await state.set_state(OrderForm.delivery_address)
        await message.answer("Укажите адрес доставки.")

    @router.message(OrderForm.delivery_address)
    async def collect_address(message: Message, state: FSMContext, bot: Bot) -> None:
        delivery_address = (message.text or "").strip()

        if not delivery_address:
            await message.answer("Напишите адрес доставки текстом.")
            return

        data = await state.get_data()
        product = catalog.get(str(data.get("product_slug", "")))

        if product is None:
            await state.clear()
            await message.answer("Товар не найден. Начните заново через /start.")
            return

        order = storage.create_order(
            source="telegram",
            product_slug=product.slug,
            product_name=product.name,
            product_price=product.price,
            customer_name=str(data["customer_name"]),
            delivery_address=delivery_address,
            telegram_contact=_telegram_contact(message),
        )
        await notify_admins(bot, config, order)
        await state.clear()
        await message.answer(
            "Спасибо за заказ! Наш менеджер скоро напишет вам по поводу оплаты."
        )

    @router.callback_query(F.data.startswith("status:"))
    async def update_status(callback: CallbackQuery) -> None:
        user_id = callback.from_user.id if callback.from_user else None

        if user_id not in config.admin_ids:
            await callback.answer("Недостаточно прав", show_alert=True)
            return

        _, order_id_raw, status = callback.data.split(":", 2)

        if status not in STATUSES:
            await callback.answer("Неизвестный статус", show_alert=True)
            return

        try:
            order = storage.update_status(int(order_id_raw), status)
        except (KeyError, ValueError):
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        await callback.message.edit_text(
            format_order(order),
            reply_markup=status_keyboard(order.id),
        )
        await callback.answer(f"Статус: {STATUSES[status]}")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
