## Live Snapshot `ams-1-vm-76ds` 2026-03-25 MSK

Этот каталог фиксирует server-only код и инфраструктурные entrypoint'ы, которые на момент `2026-03-25` не были полностью представлены в git-контуре `projects/engineer`.

Что включено:
- active cron-конфиги из `/etc/cron.d`
- wrapper'ы из `/usr/local/bin`
- live workspace `todo-integration` без `.env.runtime`, `node_modules` и runtime-данных
- локальный Bitrix app handler из `/opt/openclaw/local/bitrix_app_server.py`

Что специально не включено:
- `.env`, `.env.runtime`, токены, refresh token'ы и другие секреты
- `node_modules`, state/data, логи и временные артефакты

Редакции после импорта:
- в `usr/local/bin/send_moscow_weather.sh` Telegram token и `chat_id` заменены на безопасные placeholder'ы

Назначение:
- сохранить фактический live source of truth в GitHub
- убрать зависимость от host-only кода без git-истории
- дать основу для дальнейшей миграции server-only контуров в канонический runtime
