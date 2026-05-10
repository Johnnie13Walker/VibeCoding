# Архитектура duplicate merge platform

Дата: 2026-05-10 МСК.

## Цель

Изолированная production-grade платформа для безопасной обработки дублей сделок Bitrix24 воронки `Реанимация`.

Главное правило: сделки вручную не удалять. Любое объединение выполняется только штатным Bitrix merge после live validation.

## Структура workspace

```text
belberry/bitrix24/
  agents/                 # промпты и роли для анализа, без runtime state
  scripts/                # CLI entrypoints, тонкие wrappers
  providers/              # Bitrix/Google API abstractions
  policies/               # merge policy, risk scoring, validation rules
  integrations/
    bitrix/               # OAuth/install docs, scopes, API contracts
    google/               # Sheets contracts, service account docs
  orchestration/          # batch flows, run manifests
  tools/                  # dev tools, diagnostics, fixtures builders
  tests/
    unit/
    fixtures/
  config/                 # env examples and non-secret config
  docs/
    migration/
    runbooks/
  outputs/                # gitignored run artifacts
  logs/                   # gitignored structured logs
  state/                  # gitignored lock, ledger, OAuth state
  tmp/                    # gitignored temp files
  prompts/                # operational prompts and checklists
```

## Execution model

1. Load config from `.env`, `config/` and runtime CLI args.
2. Validate config: timezone is `Europe/Moscow`, paths are inside current workspace, secrets are present but never logged.
3. Acquire process lock.
4. Read Google Sheet snapshot.
5. Build candidate groups.
6. Validate group shape and operation key.
7. Live reconcile each deal from Bitrix.
8. Build policy plan.
9. Calculate risk score.
10. Write dry-run artifacts.
11. Stop unless explicit apply is passed.
12. Before apply, re-read CRM and compare optimistic fingerprints.
13. Apply policy normalization if allowed.
14. Execute `crm.entity.mergeBatch`.
15. Run CRM post-check.
16. Append ledger record.
17. Sync Google Sheet.
18. Run Sheet verification.
19. Release lock and write run summary.

## Safety gates

- Default mode is dry-run.
- `--apply` alone is insufficient; require explicit confirmation token like `--confirm-apply MERGE_REANIMATION_<run_id>`.
- Reject any path outside `belberry/bitrix24`.
- Reject legacy state paths and remote bridge env keys.
- Reject operation if ledger already has successful operation key.
- Reject group if source rows changed after snapshot.
- Reject group if live CRM fingerprint changed between dry-run and apply.
- Reject merge when source deals are missing, already merged, in different companies, or not matching duplicate criteria.

## Risk map

High risk:

- Wrong target deal selected.
- Group includes non-duplicates.
- Different companies or product rows.
- Contact additions before merge.
- Large activity/timeline volume.
- OAuth state copied from legacy.
- Sheet rows archived before CRM verification.
- Re-running same batch.

Mitigation:

- Deterministic target rules and visible dry-run plan.
- Live CRM verification immediately before apply.
- Conservative risk thresholds.
- Append-only ledger and process lock.
- Sheet sync after CRM post-check only.
- Manual review status instead of forced merge on conflict.

## Bitrix integration

Use OAuth local app as primary auth.

Required:

- `BELBERRY_BITRIX24_CLIENT_ID`
- `BELBERRY_BITRIX24_CLIENT_SECRET`
- `BELBERRY_BITRIX24_APP_STATE_DIR`
- `BELBERRY_BITRIX24_PORTAL_BASE_URL`

OAuth state is local and isolated under `state/bitrix-oauth/`. Refresh token rotation must persist atomically with `0600` permissions. Logs must mask access token, refresh token, webhook-like URLs and endpoints.

Minimum API surface:

- `crm.deal.get`
- `crm.deal.update`
- `crm.deal.contact.items.get`
- `crm.deal.contact.add`
- `crm.deal.productrows.get`
- `crm.activity.list`
- `crm.timeline.comment.list`
- `crm.category.list`
- `crm.status.list`
- `crm.entity.mergeBatch`

## Google integration

Use service account with access only to the target spreadsheet.

Required:

- `BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON`
- `BELBERRY_BITRIX24_DUPLICATES_SHEET_ID`
- `BELBERRY_BITRIX24_DUPLICATES_WORK_SHEET`
- `BELBERRY_BITRIX24_DUPLICATES_ARCHIVE_SHEET`
- `BELBERRY_BITRIX24_DUPLICATES_SOURCE_SHEET`

The provider must support read snapshot, guarded batch update, append archive rows and verification readback.

## Batch engine design

Core modules:

- `config_loader` - env/config/runtime args, path guard.
- `lock_manager` - process lock with stale lock detection.
- `sheet_reader` - reads rows and normalizes domains/deal IDs.
- `group_validator` - validates sheet groups.
- `crm_reconciler` - live fetch and fingerprint.
- `merge_policy` - target, field authority, conflict/risk checks.
- `merge_executor` - dry-run/apply boundary and Bitrix merge call.
- `ledger_store` - append-only operation log.
- `sheet_sync` - archive or manual-review writeback.
- `verifier` - CRM, Sheet, ledger and process verification.
- `logger` - JSONL structured logs in МСК.

Retry/recovery:

- Retry only read/API transient failures with bounded backoff.
- Never retry apply blindly after unknown result.
- If apply result is unknown, run live reconcile and classify via ledger as `needs_manual_reconcile`.
- Sheet sync can be retried after CRM success because ledger records CRM-applied/sheet-pending state.

## OAuth bootstrap

OAuth state из legacy workspace переносить запрещено. Первичная авторизация выполняется один раз вручную через локальный install handler.

Контракт state-файла `state/bitrix-oauth/install.latest.json`:

```json
{
  "saved_at": "2026-05-10T12:00:00+03:00",
  "summary": {
    "domain": "belberrycrm.bitrix24.ru",
    "member_id": "<member_id>",
    "auth_present": true,
    "refresh_present": true
  },
  "payload": {
    "auth[access_token]": "<access_token>",
    "auth[refresh_token]": "<refresh_token>",
    "auth[client_endpoint]": "https://belberrycrm.bitrix24.ru/rest",
    "auth[server_endpoint]": "https://oauth.bitrix.info/rest",
    "auth[domain]": "belberrycrm.bitrix24.ru",
    "auth[member_id]": "<member_id>",
    "auth[status]": "L"
  }
}
```

Допустимые источники payload:

1. Локальный install handler `scripts/oauth_install.py serve` — поднимает HTTP listener на `127.0.0.1:<port>`, принимает install POST из Bitrix, пишет state атомарно с `0o600`.
2. Ручная вставка через `scripts/oauth_install.py import --from-stdin` — оператор вставляет JSON, полученный из Bitrix admin → Dev tools, утилита валидирует `_payload_has_auth` и пишет state.

Запрещено:

- копирование `handler.latest.json` или `install.latest.json` из legacy `state/bitrix_app/`;
- использование `--remote-bridge`, SSH, tar dump или `_load_auth_env` из legacy;
- запись state с правами шире `0o600`;
- логирование `access_token` / `refresh_token` / полного `client_endpoint`.

Refresh token rotation выполняется тем же процессом, что и в legacy provider: атомарный `temp.replace(target)`, `0o600`, маскированные логи. После каждого refresh CLI должен писать в structured-log событие `oauth_refresh` с полями `domain`, `member_id`, `saved_at`, без секретов.

## Operation key

Каноническая формула:

```text
operation_key = "sheet=<sheet_id>|domain=<domain>|target=<target_id>|ids=<id1,id2,...>|policy=<policy_version>"
```

Правила:

- `sheet_id` — `BELBERRY_BITRIX24_DUPLICATES_SHEET_ID` на момент snapshot.
- `domain` — нормализованное значение из источника (lowercase, без `https://`, без `www.`, без trailing slash).
- `target_id` — выбранный canonical target.
- `ids` — все участники merge в порядке `target_id` first, остальные по возрастанию числового id.
- `policy_version` — константа `POLICY_VERSION` из `policies/operation_key.py`. Bumpается **вручную** при любом изменении `build_policy_plan`, порогов risk, fingerprint-схемы или contract sheet sync. Текущее значение зафиксировать в коде, в `docs/duplicate-merge-architecture.md` и в test-фикстуре.

Тест на стабильность ключа обязателен: при тех же входах ключ воспроизводится байт-в-байт; при изменении любого поля ключ меняется.

## Apply-token contract

`run_id`:

- Генерируется единожды на старте каждого run-а.
- Формат: `<YYYYMMDD>-<HHMMSS>-MSK-<8hex>`, где `8hex` — `secrets.token_hex(4)`.
- Записывается в `state/runs/<run_id>/manifest.json` синхронно до любого CRM/Sheet вызова.

`manifest.json`:

```json
{
  "run_id": "20260510-120000-MSK-<8hex>",
  "started_at_msk": "2026-05-10T12:00:00+03:00",
  "policy_version": "<policy_version>",
  "sheet_id": "<sheet_id>",
  "operation_key": "<operation_key>",
  "mode": "dry-run | apply",
  "confirm_token": "MERGE_REANIMATION_<run_id>",
  "dry_run_artifact": "outputs/runs/<run_id>/dry_run_plan.json",
  "fingerprint_at_dry_run": "<sha256>",
  "status": "dry_run_written | confirm_pending | apply_started | crm_applied | sheet_archived | failed"
}
```

Apply-engine принимает `--confirm-apply <token>` только если выполнены **все** условия:

1. `--run-id <run_id>` указан и `state/runs/<run_id>/manifest.json` существует.
2. `<token>` совпадает с `manifest.confirm_token` побайтно.
3. `manifest.mode == "dry-run"` или `manifest.status == "confirm_pending"`.
4. `manifest.dry_run_artifact` существует и читается.
5. Текущий live-fingerprint всех участников merge совпадает с `manifest.fingerprint_at_dry_run`.
6. `operation_key` отсутствует в ledger со статусом `crm_applied_*`.
7. Process lock получен (см. `lock_manager`).
8. `BELBERRY_BITRIX24_APPLY_DISABLED` не установлен в `true`.

Любое несовпадение → exit без CRM/Sheet вызовов, exit code != 0, ledger не пишется.

`confirm_token` нельзя передавать через env, нельзя писать в логи, нельзя читать из CI secrets — он живёт только в локальном manifest.json и попадает в CLI оператором копированием руками после ручного review артефакта `dry_run_plan.json`.

## Safe runbook

Dry-run:

```bash
cd /Users/pro2kuror/Desktop/VibeCoding
python -m belberry.bitrix24.scripts.duplicate_merge_batch --mode dry-run --group-domain example.ru
```

Apply, after reviewing dry-run artifact:

```bash
python -m belberry.bitrix24.scripts.duplicate_merge_batch --mode apply --run-id <run_id> --confirm-apply MERGE_REANIMATION_<run_id>
```

Current status: CLI is not implemented yet. These commands define the target interface.

## Production-ready roadmap

1. Port policy and ledger unit tests into new workspace.
2. Implement provider interfaces with fakes first.
3. Implement dry-run batch engine.
4. Add live read-only reconcile against Bitrix and Google.
5. Add structured run artifacts and logs.
6. Add apply mode with confirmation token.
7. Add post-run verification and sheet sync.
8. Add daily health-check: OAuth validity, Sheets access, stale locks, ledger gaps, failed runs.
9. Add CI tests for policy, ledger, config guard and idempotency.
10. Only after repeated successful dry-runs enable limited apply for one low-risk pair at a time.
