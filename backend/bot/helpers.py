import io


def build_startapp_link(bot_username: str, mini_app_short_name: str, project_key: str) -> str:
    username = bot_username.lstrip("@")
    short_name = mini_app_short_name.strip("/")
    return f"https://t.me/{username}/{short_name}?startapp={project_key}"


def extract_text_from_pdf_bytes(content: bytes) -> str:
    try:
        from pypdf import PdfReader

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
        from docx import Document

        doc = Document(io.BytesIO(content))
        chunks = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text and paragraph.text.strip()]
        return "\n".join(chunks).strip()
    except Exception:  # noqa: BLE001
        return ""


def should_attempt_task_extraction(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    action_markers = [
        "сделай",
        "сделать",
        "добавь",
        "добавить",
        "исправь",
        "исправить",
        "поправь",
        "поправить",
        "измени",
        "изменить",
        "обнови",
        "обновить",
        "удали",
        "удалить",
        "создай",
        "создать",
        "реализуй",
        "реализовать",
        "внедри",
        "внедрить",
        "настрой",
        "настроить",
        "протестируй",
        "протестировать",
        "почини",
        "починить",
        "оптимизируй",
        "оптимизировать",
        "нужно",
        "надо",
        "необходимо",
        "требуется",
    ]
    return any(marker in lowered for marker in action_markers)
