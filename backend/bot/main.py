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
        await message.answer(
            "Нажмите кнопку ниже, чтобы открыть Mini App в контексте этого чата.",
            reply_markup=build_web_app_keyboard(web_app_url),
        )

    @dp.message(Command("app"))
    async def cmd_app(message: Message) -> None:
        await message.answer(
            "Откройте приложение из этой кнопки, чтобы сохранить chat context.",
            reply_markup=build_web_app_keyboard(web_app_url),
        )

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
