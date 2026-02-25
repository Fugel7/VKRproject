import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.db import get_database_url


app = FastAPI(title="VKR Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TelegramAuthRequest(BaseModel):
    init_data: str


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    incoming_hash = pairs.pop("hash", None)

    if not incoming_hash:
        raise HTTPException(status_code=400, detail="Missing Telegram hash")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, incoming_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth signature")

    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Telegram auth payload expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status_code=400, detail="Missing Telegram user data")

    return json.loads(user_raw)


def save_or_update_user(telegram_user: dict) -> dict:
    tg_id = telegram_user.get("id")
    if tg_id is None:
        raise HTTPException(status_code=400, detail="Telegram user id is missing")

    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO users (tg_id, username, first_name, last_name, photo_url, last_login_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (tg_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        photo_url = EXCLUDED.photo_url,
                        last_login_at = NOW()
                    RETURNING id, tg_id, username, first_name, last_name, photo_url, created_at, last_login_at;
                    """,
                    (
                        tg_id,
                        telegram_user.get("username"),
                        telegram_user.get("first_name") or "",
                        telegram_user.get("last_name"),
                        telegram_user.get("photo_url"),
                    ),
                )
                user_row = cur.fetchone()
            conn.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while saving user: {exc}")

    return user_row


def get_user_by_tg_id(tg_id: int) -> dict | None:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, tg_id, username, first_name, last_name, photo_url, created_at, last_login_at
                    FROM users
                    WHERE tg_id = %s
                    LIMIT 1;
                    """,
                    (tg_id,),
                )
                return cur.fetchone()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading user: {exc}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "vkr-backend",
        "env": os.getenv("APP_ENV", "development"),
    }


@app.get("/me")
def me(tg_id: int) -> dict:
    user = get_user_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user": user}


@app.post("/auth/telegram")
def auth_telegram(payload: TelegramAuthRequest) -> dict:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN is not configured")

    user = verify_telegram_init_data(payload.init_data, bot_token)
    db_user = save_or_update_user(user)
    return {"ok": True, "user": user, "db_user": db_user}
