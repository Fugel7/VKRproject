import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


def _normalize_task_status(raw_status: str | None) -> str:
    if not raw_status:
        return "NEW"
    normalized = raw_status.strip().upper()
    allowed = {"NEW", "IN_PROGRESS", "DONE"}
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail="Status must be NEW, IN_PROGRESS or DONE")
    return normalized


def _extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenRouter returned empty content")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise HTTPException(status_code=502, detail="OpenRouter returned non-JSON response")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Failed to parse OpenRouter JSON output") from exc


def _extract_openrouter_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _coerce_hours(raw_value) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        value = int(round(float(raw_value)))
    else:
        digits = "".join(ch for ch in str(raw_value) if ch.isdigit())
        if not digits:
            return None
        value = int(digits)
    if value <= 0:
        return None
    return min(value, 999)


def _normalize_ai_tasks(items: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        description = str(item.get("description") or "").strip()
        raw_status = item.get("status")
        try:
            status = _normalize_task_status(raw_status if isinstance(raw_status, str) else None)
        except HTTPException:
            status = "NEW"
        normalized.append(
            {
                "title": title[:180],
                "description": description,
                "execution_hours": _coerce_hours(item.get("execution_hours")),
                "status": status,
            }
        )
    return normalized[:15]


def _split_text_to_clauses(text: str) -> list[str]:
    rough_parts = re.split(r"[\n\r;,.!?]+", text or "")
    clauses: list[str] = []
    for part in rough_parts:
        if not part.strip():
            continue
        subparts = re.split(r"\b(?:и|а|но|затем|потом)\b", part, flags=re.IGNORECASE)
        for subpart in subparts:
            cleaned = subpart.strip(" -:\t")
            if cleaned:
                clauses.append(cleaned)
    return clauses


def extract_tasks_by_rules(text: str) -> list[dict]:
    action_markers = (
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
        "настрой",
        "настроить",
        "почини",
        "починить",
        "нужно",
        "надо",
        "необходимо",
        "требуется",
    )
    project_markers = (
        "страниц",
        "карточк",
        "сайт",
        "лендинг",
        "интерфейс",
        "ui",
        "ux",
        "верстк",
        "макет",
        "фронтенд",
        "frontend",
        "бэкенд",
        "backend",
        "api",
        "endpoint",
        "роут",
        "кнопк",
        "форма",
        "модал",
        "таблиц",
        "база",
        "проект",
        "задач",
        "баг",
        "ошибк",
        "фильтр",
        "поиск",
        "авторизац",
        "товар",
    )
    tasks: list[dict] = []
    for clause in _split_text_to_clauses(text):
        lowered = clause.lower()
        has_action = any(marker in lowered for marker in action_markers)
        has_project = any(marker in lowered for marker in project_markers)
        if not has_action or not has_project:
            continue

        title = re.sub(
            r"^\s*(?:надо(?: бы)?|нужно|необходимо|требуется|не забыть бы|пожалуйста)\s+",
            "",
            clause,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"^\s*(?:сделай|сделать|добавь|добавить|исправь|исправить|измени|изменить|обнови|обновить|создай|создать|удали|удалить|реализуй|реализовать|настрой|настроить|почини|починить)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip(" .,:;-")
        if not title:
            continue
        if len(title) > 180:
            title = title[:180].rstrip()

        tasks.append(
            {
                "title": title[:1].upper() + title[1:] if title else title,
                "description": clause.strip(),
                "execution_hours": None,
                "status": "NEW",
            }
        )
    return tasks[:15]


def extract_tasks_via_openrouter(
    content_text: str,
    project_title: str,
    attachment_kind: str | None = None,
    attachment_mime: str | None = None,
    attachment_base64: str | None = None,
) -> list[dict]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured")
    text_model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
    vision_model = os.getenv("OPENROUTER_VISION_MODEL", "").strip() or text_model
    fallback_models = [
        item.strip()
        for item in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",")
        if item.strip()
    ]
    prompt = (
        "You extract project tasks from user messages for a task tracker. "
        "Return ONLY one JSON object with exact schema: "
        '{"tasks":[{"title":"string","description":"string","execution_hours":number|null,"status":"NEW|IN_PROGRESS|DONE"}]}. '
        "Rules: "
        "1) Include ONLY tasks clearly related to the current project context. "
        "2) Ignore personal, household, off-topic, joke, or unrelated requests. "
        "3) If a message mixes related and unrelated items, keep only related items. "
        "4) If project context is weak or generic, treat software/product tasks as related "
        "(site/app/bot/frontend/backend/api/design/content/analytics/integration/testing). "
        '5) If no related tasks exist, return {"tasks":[]}. '
        "6) In mixed messages like 'make tea and add checkout page', keep only the software task. "
        "7) title and description must be in Russian. If source text is another language, translate to Russian. "
        "8) Keep titles short and specific. "
        "9) execution_hours should be realistic integer estimate or null if uncertain. "
        "10) Do not output markdown or any extra text."
    )
    user_text = f"Project title: {project_title}\n\nUser message:\n{content_text}"
    user_content: str | list[dict] = user_text
    if (
        attachment_kind == "image"
        and attachment_base64
        and attachment_mime
        and attachment_mime.startswith("image/")
    ):
        user_content = [
            {"type": "text", "text": user_text + "\n\nAlso analyze the attached image content."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{attachment_mime};base64,{attachment_base64}"},
            },
        ]

    def build_request_body(use_system_prompt: bool, model_name: str, use_image: bool) -> dict:
        current_user_content: str | list[dict]
        if use_image:
            current_user_content = user_content
        else:
            current_user_content = user_text
        if use_system_prompt:
            return {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": current_user_content},
                ],
                "temperature": 0.1,
            }
        if isinstance(current_user_content, list):
            merged_content = [{"type": "text", "text": prompt}] + current_user_content
        else:
            merged_content = f"{prompt}\n\n{current_user_content}"
        return {
            "model": model_name,
            "messages": [{"role": "user", "content": merged_content}],
            "temperature": 0.1,
        }

    def send_request(request_body: dict) -> dict:
        req = Request(
            url="https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))

    def try_models(use_image: bool, models: list[str]) -> tuple[dict | None, str | None]:
        last_error: str | None = None
        for model_name in models:
            try:
                return (
                    send_request(build_request_body(use_system_prompt=True, model_name=model_name, use_image=use_image)),
                    None,
                )
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 400 and "Developer instruction is not enabled" in body:
                    try:
                        return (
                            send_request(
                                build_request_body(use_system_prompt=False, model_name=model_name, use_image=use_image)
                            ),
                            None,
                        )
                    except HTTPError as inner_exc:
                        inner_body = inner_exc.read().decode("utf-8", errors="replace")
                        last_error = f"OpenRouter error {inner_exc.code}: {inner_body}"
                        continue
                    except URLError as inner_exc:
                        last_error = f"OpenRouter is unreachable: {inner_exc}"
                        continue
                    except json.JSONDecodeError:
                        last_error = "OpenRouter response is not valid JSON"
                        continue
                last_error = f"OpenRouter error {exc.code}: {body}"
                continue
            except URLError as exc:
                last_error = f"OpenRouter is unreachable: {exc}"
                continue
            except json.JSONDecodeError:
                last_error = "OpenRouter response is not valid JSON"
                continue
        return None, last_error

    has_image = isinstance(user_content, list)
    model_candidates = [vision_model] + [m for m in fallback_models if m != vision_model]
    parsed, request_error = try_models(use_image=has_image, models=model_candidates)
    if parsed is None and has_image and content_text.strip():
        text_candidates = [text_model] + [m for m in fallback_models if m != text_model]
        parsed, request_error = try_models(use_image=False, models=text_candidates)
    if parsed is None:
        raise HTTPException(status_code=502, detail=request_error or "OpenRouter request failed")

    error_payload = parsed.get("error")
    if isinstance(error_payload, dict):
        error_message = str(error_payload.get("message") or "").strip()
        if error_message:
            raise HTTPException(status_code=502, detail=f"OpenRouter error: {error_message}")
        raise HTTPException(status_code=502, detail="OpenRouter returned an error payload")

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    content_text_raw = _extract_openrouter_text(content)
    if not content_text_raw.strip():
        return []
    try:
        payload = _extract_json_object(content_text_raw)
    except HTTPException:
        return []
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return []
    return _normalize_ai_tasks(tasks)
