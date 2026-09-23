# Threads Gaming News → Telegram

Автоматический сбор свежих игровых новостей, публикация полной версии в Telegram и короткого тизера в Threads со ссылкой на конкретный Telegram-пост.

## Что делает бот

- проверяет игровые источники каждые 10 минут;
- берёт свежие материалы за последние 72 часа;
- отсекает обзоры, гайды, скидки и другой низкоприоритетный контент;
- оценивает важность новости и публикует максимум 1 материал за запуск;
- удаляет дубли по URL, заголовку и смысловому `event_key`;
- извлекает текст статьи и `og:image`;
- Gemini делает русский заголовок, полный Telegram-текст и отдельный тизер для Threads;
- сначала публикует полную новость в Telegram;
- затем публикует тизер в Threads с прямой ссылкой на конкретный Telegram-пост;
- если Telegram уже опубликован, а Threads временно упал, следующий запуск повторяет только Threads;
- хранит историю публикаций в `data/posted.json`;
- поддерживает GitHub Actions schedule и внешний `repository_dispatch` для cron-job.org.

## Источники

IGN, GameSpot, PC Gamer, Eurogamer, Polygon, Rock Paper Shotgun, PlayStation Blog, Xbox Wire, Nintendo, Steam и StopGame.

## GitHub Secrets

Создайте в репозитории:

- `THREADS_ACCESS_TOKEN` — токен Threads API;
- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота;
- `GEMINI_API_KEY` — ключ Gemini.

Для первого `dry_run` достаточно только `GEMINI_API_KEY`: Telegram и Threads при тесте не вызываются.

## GitHub Variables

- `TELEGRAM_CHAT_ID` — канал, например `@gaming_channel`;
- `TELEGRAM_PUBLIC_USERNAME` — username канала без `@`, например `gaming_channel`;
- `TELEGRAM_FUNNEL_URL` — необязательный fallback, если канал не публичный;
- `ENABLE_AUTO_PUBLISH` — поставьте `true` только после успешного теста, чтобы включить schedule/repository_dispatch.

Бот Telegram должен быть администратором канала и иметь право публиковать сообщения.

## Запуск

Workflow содержит расписание каждые 10 минут, но автоматическая публикация включается только при `ENABLE_AUTO_PUBLISH=true`.

Для первого теста:

1. `Actions` → `Publish gaming news to Telegram and Threads`;
2. `Run workflow`;
3. оставить `dry_run = true`;
4. проверить лог;
5. затем добавить остальные секреты/переменные и запустить с `dry_run = false`.

Workflow также принимает `repository_dispatch` с `event_type: publish_gaming_news` для внешнего планировщика.

## Воронка

Threads публикует ссылку на конкретный Telegram-пост вида `https://t.me/<channel>/<message_id>`, поэтому пользователь сразу попадает на полную новость.
