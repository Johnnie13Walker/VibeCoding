# Discord Knowledge Hub MVP

MVP для связки `API -> Discord`:
- ежедневный KPI-дайджест в канал;
- idempotent sync через локальную таблицу `sync_registry` (SQLite);
- slash-команды `/kpi`, `/alerts`, `/client`.

## Структура
- `src/send_digest.py` - отправка/обновление daily digest в webhook.
- `src/bot_server.py` - endpoint Discord Interactions (`/interactions`).
- `src/register_commands.py` - регистрация slash-команд в Discord API.
- `sql/schema.sql` - SQL-схема sync-таблицы.
- `systemd/` - примеры service/timer для прод-автозапуска.

## 1) Подготовка окружения
```bash
cd "/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/discord-hub"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env`:
- `SOURCE_API_BASE_URL`, `SOURCE_API_TOKEN`
- `DISCORD_WEBHOOK_URL`
- `DISCORD_COMMAND_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`, `DISCORD_APPLICATION_ID`
- `DISCORD_DEFAULT_CHANNEL_ID`

## 2) Контракт API (минимум)
Ожидаемые endpoint-ы:
- `GET /kpi/digest`
- `GET /kpi/summary`
- `GET /alerts/recent?limit=5`
- `GET /clients/{client_id}/summary`

Пример `GET /kpi/digest`:
```json
{
  "id": "digest-2026-02-19",
  "title": "Ежедневный KPI-дайджест",
  "metrics": [
    {"name": "MRR", "value": "$125,000", "trend": "+4.2% WoW"},
    {"name": "Leads", "value": "342", "trend": "+8.0% WoW"}
  ],
  "notes": "Фокус: ускорить конверсию SQL->Deal",
  "source_url": "https://your-bi.local/dashboards/kpi"
}
```

## 3) Регистрация slash-команд
```bash
cd "/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/discord-hub"
source .venv/bin/activate
python src/register_commands.py
```

## 4) Запуск сервера команд
```bash
cd "/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/discord-hub"
source .venv/bin/activate
python src/bot_server.py
```

В Discord Developer Portal укажите Interactions URL:
- `https://<ваш-домен>/interactions`

## 5) Ручной запуск дайджеста
```bash
cd "/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/discord-hub"
source .venv/bin/activate
python src/send_digest.py
```

Логика синка:
- если контент не менялся, пост не отправляется;
- если менялся и есть `discord_message_id`, сообщение редактируется;
- если записи нет, создаётся новый пост.

## 6) Автозапуск (systemd)
В `systemd/` есть шаблоны:
- `discord-digest.service`
- `discord-digest.timer`

После адаптации путей:
```bash
sudo cp systemd/discord-digest.service /etc/systemd/system/
sudo cp systemd/discord-digest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now discord-digest.timer
```

## Важно
Discord не используем как source-of-truth. Канал хранит витрину/агрегацию, а первичные данные остаются в вашей БД/API.
