FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY common.py bot.py main.py ytdlp_helper.py \
     threads.py instagram.py youtube.py vk.py tiktok.py ./

RUN useradd --create-home --uid 1000 bot \
    && mkdir -p /app/downloads \
    && chown -R bot:bot /app

USER bot

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "bot.py"]
