# Sales report — обязательный контракт

## Sequence доставки (одной командой `--report sales --send`)

```
SALES_PRIMARY_REPORT     = "sales"
SALES_FOLLOWUP_REPORTS   = ("risks", "focus")
SALES_DISPATCH_SEQUENCE  = ("sales", "risks", "focus")
```

Источник: `shared/contracts/sales_report_contract.py`.

Health-check 09:40 ждёт три события `sales_report_sent` именно в
этом порядке, в окне «сегодня МСК ≥ 09:30», с `job_name == morning_sales_dispatch`.

## Обязательные секции (sales formatter)

Источник: `shared/contracts/sales_report_format_contract.py`.

### `sales` — Sales Copilot

- 📊 Сводка по продажам
- Итоги за прошлый рабочий день
- Воронка
- На стадии договора
- Источники новых сделок

### `risks` — Риски по сделкам

- ⚠️ Риски по сделкам
- Без движения > 14 дн.
- Без следующего шага
- Без коммуникации > 14 дн.
- Сделки с просрочками

### `focus` — Фокус РОПа

- 🎯 Фокус РОПа
- Что РОП обязан сделать сегодня:
- 🔥 Молодцы за вчера

При отсутствии секции → `sales_report_error` со `stage=format_validation`.
Отправка может продолжиться, но `sales_dispatch_complete.ok=false`.

## Sales scope

Источник: `apps/lev_petrovich/legacy_sales_agent/sales_team_scope.py`.

Включаются департаменты:

- Группа продаж Belberry
- Группа продаж Acoola Team
- Телемаркетинг

Исключаются: руководители/служебные/интеграторы по
position/name/department markers.

Override через env:

- `SALES_DEPARTMENT_IDS`
- `SALES_DEPARTMENT_NAMES`
- `SALES_EXCLUDED_USER_IDS`
- `SALES_EXCLUDED_USER_NAMES`
- `SALES_EXCLUDED_USER_MARKERS`

## Bitrix entities, читаемые snapshot'ом

| что | метод | фильтр |
|-----|-------|--------|
| текущий пользователь | `user.current` | — |
| пользователи | `user.get` | — |
| департаменты | `department.get` | — |
| sales-сделки | `crm.deal.list` | `CATEGORY_ID=10` |
| активные сделки | `crm.deal.list` | `CLOSED=N` |
| закрытые сделки | `crm.deal.list` | `CLOSED=Y` |
| статусы | `crm.status.list` | по stage / source |
| поля сделки | `crm.deal.fields` | — |
| компании | `crm.company.list` | — |
| контакты | `crm.contact.list` | — |
| активности | `crm.activity.list` | по сделкам |
| задачи | `tasks.task.list` (или webhook) | по sales-юзерам |
| встречи (SP) | `crm.item.list` | entity 1048, category 24 |
| брифы (SP) | `crm.item.list` | entity 1056, category 28 |

Stage маркеры:

- `MEETING_DONE_STAGE_NAME = "Встреча проведена"`
- `BRIEF_ACCEPTED_STAGE_NAME = "Бриф принят производством"`

## Wazzup

- архив: `/opt/openclaw/state/bitrix_app/wazzup.*.json`
- провайдер: `cloudbot/providers/wazzup_provider.py`
- telegroup отфильтровывается
- считаются messenger dialogs/messages, incoming/outgoing
