# Env Examples Contract

Дата фиксации: 2026-04-28 МСК.

Статус: contract only. Этот документ не меняет env loading, live env, runtime, cron, systemd, docker или deploy scripts.

## 1. Purpose

`config/env/examples/` хранит только example-файлы.

Example-файл описывает имена переменных и безопасные placeholder/default значения. Он не является runtime config.

## 2. What is allowed in examples

Разрешено:

- пустые значения;
- безопасные default значения вроде `duckduckgo`;
- комментарии с назначением переменной;
- redacted placeholders;
- ссылки на schema/contract docs.

Запрещено:

- реальные API keys;
- Telegram bot tokens;
- chat ids для live routing;
- private keys;
- VPN config;
- `.env`;
- `.env.local`;
- `.env.production`;
- runtime-generated config.

## 3. Shared env

Shared env examples могут описывать только общие технические настройки:

```text
OPENAI_API_KEY
BITRIX_APP_STATE_DIR
SEARCH_PROVIDER
SEARCH_BASE_URL
SEARCH_ENGINE
SEARCH_TIMEOUT_SECONDS
SENTRY_*
```

Shared env не должен задавать agent identity.

## 4. Agent-specific env

Agent-specific env должен быть раздельным для контуров:

```text
Larisa:
LARISA_TELEGRAM_CHAT_ID
LARISA_TELEGRAM_BOT_TOKEN
LARISA_TELEGRAM_DRY_RUN

Lev/Sales:
SALES_TELEGRAM_CHAT_ID
SALES_TELEGRAM_OWNER_ID
SALES_TELEGRAM_DM_CHAT_ID
SALES_WEEKLY_TELEGRAM_CHAT_ID
SALES_TELEGRAM_BOT_TOKEN
```

Эти переменные нельзя смешивать без отдельного routing approval.

## 5. TELEGRAM_BOT_TOKEN rule

Нельзя использовать общий `TELEGRAM_BOT_TOKEN` как silent fallback для agent identity.

Причина:

- Лариса и Lev/Sales имеют разные delivery/chat-routing expectations;
- общий fallback может отправить сообщение не в тот контур;
- ошибка token/chat routing является production-critical.

Допустимый future contract:

```text
LARISA_TELEGRAM_BOT_TOKEN for Larisa
SALES_TELEGRAM_BOT_TOKEN for Lev/Sales
TELEGRAM_BOT_TOKEN only if explicitly documented as shared gateway token
```

Любой fallback должен быть явным, протестированным и approved.

## 6. Current migrated examples

```text
config/env/examples/app_config.env.example
config/env/examples/integrations.env.example
```

Они перенесены как examples. Это не approval на live env migration.

## 7. No-touch

Запрещено в рамках env examples work:

- менять live env;
- менять env loading;
- менять cron/systemd/docker;
- менять runtime pointers;
- менять deploy scripts;
- менять production code;
- менять `configs/schedule_contract.env`;
- менять `configs/schedules.cron`.

## 8. Verification

После изменений в env examples docs:

```bash
rg -n "shared env|agent-specific|TELEGRAM_BOT_TOKEN|no secrets|examples only" docs/migration/wave5/env_examples_contract.md
python3 -m unittest discover -s tests/unit
```

## 9. Verdict

```text
env examples contract documented
runtime env remains no-touch
```
