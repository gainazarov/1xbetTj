import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from db import init_db
from handlers_start import router as start_router
from handlers_admin import router as admin_router
from handlers_mailings import router as mailings_router, scheduled_mailings_worker
from handlers_channel import router as channel_router


async def main() -> None:
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(mailings_router)
    dp.include_router(channel_router)

    # Фоновый планировщик запланированных рассылок
    asyncio.create_task(scheduled_mailings_worker(bot))

    logging.info("Бот запускается. Админы: %s", ADMIN_IDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
