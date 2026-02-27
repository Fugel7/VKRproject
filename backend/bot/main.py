import asyncio
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo


def build_web_app_keyboard(web_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=web_app_url))]
        ]
    )


def build_url_keyboard(url: str, text: str = "Открыть приложение") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, url=url)]
        ]
    )


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def build_startapp_link(bot_username: str, mini_app_short_name: str, project_key: str) -> str:
    username = bot_username.lstrip("@")
    short_name = mini_app_short_name.strip("/")
    return f"https://t.me/{username}/{short_name}?startapp={project_key}"


def ensure_chat_project_via_backend(
    backend_base_url: str,
    bot_internal_token: str,
    chat_id: int,
    chat_type: str | None,
    title: str | None,
) -> dict:
    url = f"{backend_base_url.rstrip('/')}/bot/chat-project"
    payload = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
    }
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Bot-Token": bot_internal_token,
        },
    )
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            if not parsed.get("ok") or not isinstance(parsed.get("project"), dict):
                raise RuntimeError(f"Unexpected backend response: {raw}")
            return parsed["project"]
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Backend {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Backend is unreachable: {exc}") from exc


async def main() -> None:
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    web_app_url = get_required_env("WEB_APP_URL")
    bot_username = get_required_env("BOT_USERNAME")
    mini_app_short_name = get_required_env("MINI_APP_SHORT_NAME")
    backend_internal_url = get_required_env("BACKEND_INTERNAL_URL")
    bot_internal_token = get_required_env("BOT_INTERNAL_TOKEN")

    bot = Bot(token=token)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Откройте приложение кнопкой ниже.",
            reply_markup=build_web_app_keyboard(web_app_url),
        )

    @dp.message(Command("app"))
    async def cmd_app(message: Message) -> None:
        if message.chat.type == "private":
            await message.answer(
                "Откройте приложение кнопкой ниже.",
                reply_markup=build_web_app_keyboard(web_app_url),
            )
            return

        chat_title = message.chat.title or "Новый проект"
        try:
            project = await asyncio.to_thread(
                ensure_chat_project_via_backend,
                backend_internal_url,
                bot_internal_token,
                int(message.chat.id),
                str(message.chat.type),
                chat_title,
            )
            deep_link = build_startapp_link(bot_username, mini_app_short_name, str(project["project_key"]))
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"Не удалось подготовить проект для чата: {exc}")
            return

        await message.answer(
            "Откройте Mini App по кнопке ниже. Пользователь попадет в проект этого чата.",
            reply_markup=build_url_keyboard(deep_link),
        )

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
