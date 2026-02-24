import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "vkr-backend",
        "env": os.getenv("APP_ENV", "development"),
    }


@app.post("/auth/telegram")
def auth_telegram(payload: TelegramAuthRequest) -> dict:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN is not configured")

    user = verify_telegram_init_data(payload.init_data, bot_token)
    return {"ok": True, "user": user}
