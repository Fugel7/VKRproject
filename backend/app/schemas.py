from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: str
    start_param: str | None = None
    unsafe_chat_id: int | None = None
    unsafe_chat_type: str | None = None
    unsafe_chat_title: str | None = None


class BotChatProjectRequest(BaseModel):
    chat_id: int
    chat_type: str | None = None
    title: str | None = None


class BotIngestMessageRequest(BaseModel):
    chat_id: int
    chat_type: str | None = None
    title: str | None = None
    user_tg_id: int
    user_username: str | None = None
    user_first_name: str | None = None
    user_last_name: str | None = None
    content_text: str
    source_type: str | None = None
    attachment_kind: str | None = None
    attachment_mime: str | None = None
    attachment_base64: str | None = None


class SprintCreateRequest(BaseModel):
    tg_id: int
    title: str
    start_date: str | None = None
    end_date: str | None = None


class SprintUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    is_open: bool | None = None
    start_date: str | None = None
    end_date: str | None = None


class TaskCreateRequest(BaseModel):
    tg_id: int
    title: str
    description: str = ""
    execution_hours: int | None = None
    status: str | None = None
    sprint_id: int | None = None


class TaskUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    description: str | None = None
    execution_hours: int | None = None
    status: str | None = None
    sprint_id: int | None = None


class CommentCreateRequest(BaseModel):
    tg_id: int
    text: str
