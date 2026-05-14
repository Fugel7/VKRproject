FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WHISPER_CACHE_DIR=/opt/whisper-cache

ARG WHISPER_MODEL=tiny
ARG PRELOAD_WHISPER_MODEL=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p "${WHISPER_CACHE_DIR}" \
    && if [ "${PRELOAD_WHISPER_MODEL}" = "1" ]; then \
        WHISPER_MODEL="${WHISPER_MODEL}" python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ.get('WHISPER_MODEL', 'tiny'), device='cpu', compute_type='int8', download_root=os.environ['WHISPER_CACHE_DIR'])"; \
    fi

COPY app ./app
COPY bot ./bot
COPY scripts ./scripts
COPY schema.sql ./schema.sql

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
