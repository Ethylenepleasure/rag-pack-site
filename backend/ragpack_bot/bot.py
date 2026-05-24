from __future__ import annotations

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .catalog import Catalog, Product
from .config import Config
from .notifications import format_order, notify_admins, status_keyboard
from .storage import OrderStorage, STATUSES


class OrderForm(StatesGroup):
    product_slug = State()
    customer_name = State()
    delivery_address = State()


CATEGORIES = {
    "bags": "Сумки",
    "accessories": "Аксессуары",
    "cases": "Чехлы",
}


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сумки", callback_data="category:bags")],
            [InlineKeyboardButton(text="Аксессуары", callback_data="category:accessories")],
            [InlineKeyboardButton(text="Чехлы", callback_data="category:cases")],
            [InlineKeyboardButton(text="Телега креатора", url="https://t.me/ragpackleather")],
        ]
    )


def _product_keyboard(product: Product) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Выбрать {product.name}", callback_data=f"order:{product.slug}")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="menu")],
        ]
    )


def _telegram_contact(message: Message) -> str:
    user = message.from_user

    if user is None:
        return "unknown"

    if user.username:
        return f"@{user.username} / {user.id}"

    return str(user.id)


def _product_line(product: Product) -> str:
    return f"{product.name} / {product.price}"


async def _send_main_menu(message: Message, config: Config) -> None:
    caption = "RĄG PACK//\n\nВыберите раздел:"
    image_path = config.catalog_path.parent / "assets/menu-cover.jpg"

    if image_path.exists():
        await message.answer_photo(
            FSInputFile(image_path),
            caption=caption,
            reply_markup=_main_menu_keyboard(),
        )
        return

    await message.answer(caption, reply_markup=_main_menu_keyboard())


async def _send_product_card(message: Message, config: Config, product: Product) -> None:
    caption = "\n".join(
        (
            f"{product.name} / {product.price}",
            product.tag,
            "",
            product.description,
        )
    )
    image_path = config.catalog_path.parent / product.image

    if image_path.exists():
        await message.answer_photo(
            FSInputFile(image_path),
            caption=caption,
            reply_markup=_product_keyboard(product),
        )
        return

    await message.answer(caption, reply_markup=_product_keyboard(product))


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

        await _send_main_menu(message, config)

    @router.callback_query(F.data == "menu")
    async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await _send_main_menu(callback.message, config)
        await callback.answer()

    @router.callback_query(F.data.startswith("category:"))
    async def show_category(callback: CallbackQuery) -> None:
        category = callback.data.split(":", 1)[1] if callback.data else ""
        products = catalog.by_category(category)

        if not products:
            await callback.answer("Раздел пуст", show_alert=True)
            return

        title = CATEGORIES.get(category, "Раздел")
        await callback.message.answer(f"{title}:")

        for product in products:
            await _send_product_card(callback.message, config, product)

        await callback.answer()

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
