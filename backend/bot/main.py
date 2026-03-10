import asyncio
import base64
import io
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from docx import Document
from pypdf import PdfReader


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


def ingest_message_via_backend(
    backend_base_url: str,
    bot_internal_token: str,
    payload: dict,
) -> dict:
    url = f"{backend_base_url.rstrip('/')}/bot/ingest-message"
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
        with urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            if not parsed.get("ok"):
                raise RuntimeError(f"Unexpected backend response: {raw}")
            return parsed
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Backend {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Backend is unreachable: {exc}") from exc


def extract_text_from_pdf_bytes(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        chunks = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks.append(page_text)
        return "\n".join(chunks).strip()
    except Exception:  # noqa: BLE001
        return ""


def extract_text_from_docx_bytes(content: bytes) -> str:
    try:
        doc = Document(io.BytesIO(content))
        chunks = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text and paragraph.text.strip()]
        return "\n".join(chunks).strip()
    except Exception:  # noqa: BLE001
        return ""


async def download_telegram_file_bytes(bot: Bot, file_id: str) -> bytes:
    file_info = await bot.get_file(file_id)
    stream = io.BytesIO()
    await bot.download(file_info, destination=stream)
    return stream.getvalue()


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

    @dp.message()
    async def ingest_tasks_from_message(message: Message) -> None:
        if not message.from_user or message.from_user.is_bot:
            return
        base_text = (message.text or message.caption or "").strip()
        if base_text.startswith("/"):
            return

        source_type = "text"
        if message.caption:
            source_type = "caption"
        elif message.voice:
            source_type = "voice"
        elif message.video:
            source_type = "video"
        elif message.document:
            source_type = "document"
        elif message.audio:
            source_type = "audio"

        document_text = ""
        attachment_kind = None
        attachment_mime = None
        attachment_base64 = None

        try:
            if message.document:
                source_type = "document"
                doc_bytes = await download_telegram_file_bytes(bot, message.document.file_id)
                file_name = (message.document.file_name or "").lower()
                mime = (message.document.mime_type or "").lower()
                if mime.startswith("text/") or file_name.endswith(".txt") or file_name.endswith(".md"):
                    try:
                        document_text = doc_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        document_text = doc_bytes.decode("cp1251", errors="ignore")
                elif mime == "application/pdf" or file_name.endswith(".pdf"):
                    document_text = extract_text_from_pdf_bytes(doc_bytes)
                elif (
                    mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    or file_name.endswith(".docx")
                ):
                    document_text = extract_text_from_docx_bytes(doc_bytes)
                else:
                    await message.reply(
                        "Пока поддерживаются файлы TXT/PDF/DOCX. "
                        "Для других форматов добавьте текст с задачами в подпись."
                    )
            elif message.photo:
                source_type = "image"
                best_photo = message.photo[-1]
                image_bytes = await download_telegram_file_bytes(bot, best_photo.file_id)
                if len(image_bytes) > 4 * 1024 * 1024:
                    await message.reply("Изображение слишком большое. Отправьте файл до 4 МБ.")
                    return
                attachment_kind = "image"
                attachment_mime = "image/jpeg"
                attachment_base64 = base64.b64encode(image_bytes).decode("ascii")
        except Exception as exc:  # noqa: BLE001
            await message.reply(f"Не удалось прочитать вложение: {exc}")
            return

        text_parts = []
        if base_text:
            text_parts.append(base_text)
        if document_text.strip():
            text_parts.append("Текст из файла:\n" + document_text.strip())
        text = "\n\n".join(text_parts).strip()

        if not text and not attachment_base64:
            await message.reply(
                "Не удалось получить данные для анализа. "
                "Добавьте текст/подпись или отправьте файл TXT/PDF/DOCX, либо изображение."
            )
            return

        payload = {
            "chat_id": int(message.chat.id),
            "chat_type": str(message.chat.type),
            "title": message.chat.title or "Личный проект",
            "user_tg_id": int(message.from_user.id),
            "user_username": message.from_user.username,
            "user_first_name": message.from_user.first_name,
            "user_last_name": message.from_user.last_name,
            "content_text": text,
            "source_type": source_type,
            "attachment_kind": attachment_kind,
            "attachment_mime": attachment_mime,
            "attachment_base64": attachment_base64,
        }
        try:
            result = await asyncio.to_thread(
                ingest_message_via_backend,
                backend_internal_url,
                bot_internal_token,
                payload,
            )
        except Exception as exc:  # noqa: BLE001
            await message.reply(f"Не удалось извлечь задачи: {exc}")
            return

        created = result.get("created_tasks") or []
        created_count = int(result.get("created_count") or 0)
        if created_count <= 0:
            await message.reply("Задачи не найдены. Попробуйте описать задачи более явно.")
            return

        preview_lines = []
        for index, task in enumerate(created[:5], start=1):
            title = str(task.get("title") or "").strip() or f"Задача {index}"
            hours = task.get("execution_hours")
            suffix = f" ({hours} ч)" if hours else ""
            preview_lines.append(f"{index}. {title}{suffix}")
        extra = f"\n... и еще {created_count - 5}" if created_count > 5 else ""
        await message.reply(f"Создал задач: {created_count}\n" + "\n".join(preview_lines) + extra)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
