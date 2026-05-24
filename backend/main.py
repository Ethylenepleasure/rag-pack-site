from __future__ import annotations

import asyncio

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from ragpack_bot.bot import create_dispatcher
from ragpack_bot.catalog import Catalog
from ragpack_bot.config import load_config
from ragpack_bot.http import create_app
from ragpack_bot.storage import OrderStorage


async def run_http(app: web.Application, host: str, port: int) -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def main() -> None:
    config = load_config()
    catalog = Catalog.from_file(config.catalog_path)
    storage = OrderStorage(config.database_path)
    storage.init()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Меню"),
        ]
    )
    dispatcher = create_dispatcher(config, catalog, storage)
    app = create_app(config, bot, catalog, storage)

    await asyncio.gather(
        dispatcher.start_polling(bot),
        run_http(app, config.host, config.port),
    )


if __name__ == "__main__":
    asyncio.run(main())
