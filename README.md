# video-download

Telegram-бот: пришли ссылку — получишь видео файлом.

Поддерживает: **Threads**, **Instagram**, **YouTube / Shorts**, **VK**, **TikTok**.

## Быстрый старт (локально)

```bash
cp .env.example .env
# Впиши TELEGRAM_BOT_TOKEN от @BotFather

uv sync
uv run python bot.py
```

CLI без бота:

```bash
uv run python main.py "https://www.youtube.com/shorts/..."
```

## Деплой на сервер (Docker Compose)

Требования: Docker + Docker Compose plugin.

```bash
git clone <repo> && cd video-download
cp .env.example .env
# Отредактируй .env: токен и желательно ALLOWED_USER_IDS

docker compose up -d --build
```

Логи:

```bash
docker compose logs -f bot
```

Обновление:

```bash
git pull
docker compose up -d --build
```

Остановка:

```bash
docker compose down
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather (обязательно) |
| `ALLOWED_USER_IDS` | Список Telegram user id через запятую; пусто = всем |
| `MAX_CONCURRENT_DOWNLOADS` | Макс. параллельных скачиваний (по умолчанию `3`) |

Свой id можно узнать у [@userinfobot](https://t.me/userinfobot).

## Ограничения

- Telegram принимает от бота файлы до ~50 МБ.
- Приватные / удалённые посты не скачиваются.
- С одного IP платформы могут ограничивать частые запросы (особенно TikTok / Instagram).
- У пользователя одновременно обрабатывается только одна ссылка.
