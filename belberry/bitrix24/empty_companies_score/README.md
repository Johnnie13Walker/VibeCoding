# empty_companies_score

Ежедневный скоринг placeholder-карточек компаний в Bitrix24 Belberry — триаж для удаления через [crm_deal_merge/scripts/delete_strict_empty_companies.py](../crm_deal_merge/scripts/delete_strict_empty_companies.py).

Параллельный канал к [`dup_sheet_sync.py`](../dup_sheet_sync.py): тот ловит дубли по ИНН (27% портала), а этот скоринг работает с 73% «голых» — компаниями без реквизитов.

## Логика скоринга

Для каждой компании считаются три бинарных флага:

| Флаг | Условие |
|---|---|
| `empty_links` | 0 deals + 0 contacts + 0 leads |
| `empty_inn` | в `crm.requisite.list` для company нет непустого `RQ_INN` |
| `empty_uf` | все 4 UF-поля пусты (`Бренд`, `Город`, `Сайт`, `Оборот`) |

**Score = sum(флаги) → 0..3.**

**`safe_to_delete = empty_links`** — отдельный, более строгий критерий: если у компании 0 привязанных сущностей, её можно удалить независимо от ИНН/UF, никто не потеряет данные.

## Что попадает во вкладку

Вкладка `Пустые компании (скоринг)` (gid=1756722113) в книге `13L0gqwk…`.

- **Фильтр:** `score >= 2 OR safe_to_delete=True`. Score 0/1 не интересны (слишком много шума при малой уверенности).
- **Сортировка:** `score desc, date_create asc` — самые пустые сверху, среди равных — самые старые первыми.
- **Визуал:** score=3 красный, score=2 жёлтый, `safe_to_delete=да` зелёный + bold.

## Расписание

На VPS (см. `deploy/install.sh`):

| Время МСК | Время UTC | Флаг | Что |
|---|---|---|---|
| 09:30 | 06:30 | `--notify` | Полный прогон + TG-сводка Ларисе с дельтой |
| 18:30 | 15:30 | — | Полный прогон без TG (просто перезапись вкладки) |

CRON_TZ на этом VPS не работает — выражения зашиты в UTC (МСК - 3).

## TG-сводка

Шлётся один раз в день после утреннего прогона. Содержит текущие цифры (score=3+safe, score=3, score=2, safe, total) + дельту за сутки + ссылку на вкладку. Канал — личный бот Ларисы Ивановны (chat_id из env `LARISA_TELEGRAM_CHAT_ID`).

Дельта считается по предыдущему snapshot в `<DATA_DIR>/state.json` — после каждого прогона state перезаписывается.

## Запуск

```bash
# локально (мак) — dry-run, не пишет в Sheet и не шлёт TG
python -m empty_companies_score --dry-run

# на VPS — продовый прогон через cron
sudo bash deploy/install.sh   # один раз: установка пакета в venv + cron-записи
```

## Структура

```
empty_companies_score/
├── empty_companies_score/
│   ├── __init__.py
│   ├── __main__.py        # python -m empty_companies_score
│   ├── bitrix_client.py   # OAuth + retry + пагинация
│   ├── config.py          # env-конфиг
│   ├── fetcher.py         # 5 fetch + batch user.get
│   ├── scorer.py          # ScoredCompany, score_companies, select_for_upload, summary_counts
│   ├── uploader.py        # запись в Sheets с цветовым форматированием
│   ├── notifier.py        # state.json дельта + TG
│   └── cli.py             # argparse, --notify / --dry-run
├── deploy/install.sh
├── tests/test_scorer.py
├── pyproject.toml
└── README.md
```

## Дешевле сделать иначе?

`fetch_all` тянет всех 26 261 компаний полностью каждый прогон (~7-8 мин). Это сейчас прагматичный choice — Bitrix REST не даёт incremental cursor по DATE_MODIFY дешевле, чем по `>ID`. Если станет узким местом, можно:

1. Кэшировать `companies.json` и сверять по `DATE_MODIFY` через `filter[>DATE_MODIFY]=last_seen` (требует доработки `paginate`).
2. Уйти на listing API `crm.company.search`/`crm.statistics.entity.fields` — но они не отдают UF.

Сейчас ~8 мин 2× в день = ~16 мин/сутки. На фоне `dup_sheet_sync` (~2 мин/прогон) — приемлемо.
