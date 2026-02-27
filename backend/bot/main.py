import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo


def build_web_app_keyboard(web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=web_app_url))]
        ]
    )


def build_open_url_keyboard(web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть по ссылке", url=web_app_url)]
        ]
    )


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


async def main() -> None:
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    web_app_url = get_required_env("WEB_APP_URL")

    bot = Bot(token=token)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if message.chat.type == "private":
            await message.answer(
                "Нажмите кнопку ниже, чтобы открыть Mini App.",
                reply_markup=build_web_app_keyboard(web_app_url),
            )
            return

        await message.answer(
            "В группах Telegram может блокировать web_app-кнопку. "
            "Откройте приложение по ссылке или напишите боту в личку /start.",
            reply_markup=build_open_url_keyboard(web_app_url),
        )

    @dp.message(Command("app"))
    async def cmd_app(message: Message) -> None:
        if message.chat.type == "private":
            await message.answer(
                "Откройте приложение кнопкой ниже.",
                reply_markup=build_web_app_keyboard(web_app_url),
            )
            return

        await message.answer(
            "В этом чате web_app-кнопка недоступна для этого бота. "
            "Откройте по ссылке или используйте личный чат с ботом (/start).",
            reply_markup=build_open_url_keyboard(web_app_url),
        )

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
