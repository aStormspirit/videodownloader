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

Активность пользователей (кто скачивал):

```bash
docker compose logs -f bot | grep Download
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
| `DONATE_STARS` | Сумма доната в Telegram Stars на кнопке (по умолчанию `50`) |
| `YTDLP_COOKIES_FILE` | Путь к `cookies.txt` для YouTube (в Docker: `/app/cookies.txt`) |

Свой id можно узнать у [@userinfobot](https://t.me/userinfobot).

## YouTube: cookies (обязательно на VPS)

С IP датацентров YouTube часто отвечает `Sign in to confirm you're not a bot`. Нужен файл cookies:

1. Открой **Incognito** → войди в YouTube (лучше отдельный аккаунт).
2. В той же вкладке открой `https://www.youtube.com/robots.txt`.
3. Экспортируй cookies для `youtube.com` расширением (**Get cookies.txt LOCALLY** / **cookies.txt**).
4. Закрой Incognito (чтобы сессия не ротировалась в браузере).
5. Сохрани файл как `cookies.txt` в корне проекта и на сервере:

```bash
# локально → сервер
scp -i ~/Загрузки/legion.pem cookies.txt ubuntu@16.16.170.143:~/video-download/cookies.txt

ssh -i ~/Загрузки/legion.pem ubuntu@16.16.170.143
cd ~/video-download
sudo docker compose up -d --build
```

`cookies.txt` в git не коммитится. Не качай слишком часто с одного аккаунта — риск бана.

Образ Docker ставит **Node.js 22** — yt-dlp решает YouTube JS-challenge (EJS) через него.

## Ограничения

- Telegram принимает от бота файлы до ~50 МБ.
- Приватные / удалённые посты не скачиваются.
- С одного IP платформы могут ограничивать частые запросы (особенно TikTok / Instagram / YouTube).
- У пользователя одновременно обрабатывается только одна ссылка.
