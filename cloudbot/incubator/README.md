# cloudbot/incubator/

Инкубатор экспериментальных модулей и расширений Cloudbot. По соглашению (см. `shared/docs/architecture/system_map.md`) — это **НЕ канонический runtime**, а sandbox для прототипов.

## Содержимое

- `openclaw-extensions/` — экспериментальные расширения (Telegram CRM-lite + Search + Steps + Discord-hub + DevOps-SRE). Перенесено из `~/Desktop/OpenClo/incubator/openclaw-extensions/` 2026-05-28.

## Правила

- Код здесь не считается production-grade.
- Перед использованием в боевом runtime — миграция в `cloudbot/apps/`, `cloudbot/cloudbot/workflows/`, `cloudbot/agents/` через явный design + смену контракта.
- См. AGENTS.md внутри `openclaw-extensions/`: «работать только через оркестратор».
