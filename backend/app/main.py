from fastapi import FastAPI
import os


app = FastAPI(title="VKR Backend", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "vkr-backend",
        "env": os.getenv("APP_ENV", "development"),
    }
