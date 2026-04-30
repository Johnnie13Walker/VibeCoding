# Provider: bitrix app-state

Этот слой отвечает за доступ к Bitrix24 через локальное приложение и сохраненный OAuth state.

- Источник правды: `install.latest.json` / `handler.latest.json` в `BITRIX_APP_STATE_DIR`.
- Входящих webhook-ов Bitrix в runtime больше нет.
- Бизнес-логика остается в workflow/skills, а здесь только API и state access.
