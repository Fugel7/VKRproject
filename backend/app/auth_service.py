import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.db import get_database_url


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

    user = json.loads(user_raw)
    context = {
        "chat_instance": pairs.get("chat_instance"),
        "chat_type": pairs.get("chat_type"),
        "start_param": pairs.get("start_param"),
    }

    chat_raw = pairs.get("chat")
    if chat_raw:
        try:
            context["chat"] = json.loads(chat_raw)
        except json.JSONDecodeError:
            context["chat"] = None

    return {"user": user, "context": context}


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
            return user_row
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while saving user: {exc}")


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
