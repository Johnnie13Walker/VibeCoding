# DISCOVERY — Belberry Sales KPI Dashboard

- Дата запуска: 2026-05-20T16:47:28+03:00
- Портал: belberrycrm.bitrix24.ru
- Режим: read-only, write-методы Bitrix не вызывались.

## Bootstrap

- Bitrix profile: OK ID=2812 NAME=Лариса ADMIN=True

## 1. Направления продуктов

### crm.dealcategory.list

| ID | NAME | direction_hint |
|---|---|---|
| 10 | Продажи |  |
| 16 | Аккаунтинг OLD |  |
| 22 | Аккаунтинг NEW |  |
| 28 | Проекты |  |
| 40 | Retention — Отвалы |  |
| 44 | Retention — Оплачено |  |
| 50 | Телемаркетинг |  |

### crm.deal.fields — enum-кандидаты

| FIELD_ID | LABEL | TYPE | ENUM_VALUES |
|---|---|---|---|
| — | — | — | — |

### crm.type.list — smart-processes

| entityTypeId | TITLE |
|---|---|
| 1040 | Данные для дашборда |
| 1044 | Данные для дашборда (стадии сделки) |
| 1048 | Встречи |
| 1052 | Импорт баз |
| 1056 | Брифы |
| 1064 | Должностные обязанности |
| 1068 | Оформление сотрудника |
| 1074 | Увольнение сотрудника |
| 1078 | Отпуск сотрудника |
| 1082 | Карточка сотрудника |
| 1086 | Копирайтинг |
| 1090 | Архив_Дизайн |
| 1094 | Биржа |
| 1106 | КП |
| 1110 | Договор |

**BLOCKER:** явный механизм СППВР/ИИ/Аналитика/Справочник не найден в категориях, UF enum и smart-process title.

## 2. Тип активити «встреча»

### crm.activity.fields — поля с подсказками first/repeat

| FIELD_ID | LABEL | TYPE | VALUES |
|---|---|---|---|
| — | — | — | — |

### 50 свежих activity TYPE_ID=1

| ID | SUBJECT | OWNER_TYPE_ID | OWNER/DEAL | COMPLETED | CREATED |
|---|---|---|---|---|---|
| 201282 | Встреча с Лидия | 3 | 17570 | Y | 2023-09-25T13:10:47+03:00 |
| 200528 | Первая встреча | 1 | 226992 | Y | 2023-09-22T12:13:38+03:00 |
| 200326 | Первая встреча | 1 | 230034 | Y | 2023-09-21T17:25:51+03:00 |
| 200280 | Первая встреча | 1 | 65554 | Y | 2023-09-21T16:28:31+03:00 |
| 199634 | Первая встреча | 3 | 16184 | Y | 2023-09-20T15:05:59+03:00 |
| 199626 | Первая встреча | 3 | 17534 | Y | 2023-09-20T15:01:14+03:00 |
| 199606 | Первая встреча | 1 | 1891 | Y | 2023-09-20T14:30:12+03:00 |
| 199452 | Первая встреча | 1 | 229506 | Y | 2023-09-20T12:01:40+03:00 |
| 199152 | Первая встреча | 3 | 17522 | Y | 2023-09-19T12:37:02+03:00 |
| 198872 | Первая встреча | 1 | 223622 | Y | 2023-09-18T13:25:34+03:00 |
| 198862 | Первая встреча | 1 | 68102 | Y | 2023-09-18T13:11:40+03:00 |
| 198760 | Первая встреча | 1 | 223710 | Y | 2023-09-18T11:26:40+03:00 |
| 198640 | Первая встреча | 1 | 209904 | Y | 2023-09-15T17:21:16+03:00 |
| 198380 | Первая встреча | 1 | 220820 | Y | 2023-09-15T13:39:36+03:00 |
| 197966 | Первая встреча | 1 | 209268 | Y | 2023-09-14T15:58:04+03:00 |
| 197932 | Первая встреча | 1 | 223708 | Y | 2023-09-14T15:27:06+03:00 |
| 197728 | Первая встреча | 1 | 223704 | Y | 2023-09-14T13:27:41+03:00 |
| 197516 | Первая встреча | 3 | 17472 | Y | 2023-09-14T11:40:00+03:00 |
| 196970 | Первая встреча | 1 | 222450 | Y | 2023-09-13T12:06:26+03:00 |
| 196864 | Первая встреча | 1 | 212442 | Y | 2023-09-13T09:46:38+03:00 |
| 195903 | Первая встреча | 1 | 232379 | Y | 2023-09-08T18:25:52+03:00 |
| 195547 | Первая встреча | 1 | 3920 | Y | 2023-09-08T12:22:33+03:00 |
| 195527 | Первая встреча | 1 | 232270 | Y | 2023-09-08T11:45:17+03:00 |
| 194624 | Первая встреча | 1 | 2885 | Y | 2023-09-06T13:29:59+03:00 |
| 194200 | Первая встреча | 1 | 6634 | Y | 2023-09-05T15:42:48+03:00 |
| 193594 | Первая встреча | 1 | 2325 | Y | 2023-09-04T18:06:27+03:00 |
| 193588 | Первая встреча | 1 | 137896 | Y | 2023-09-04T17:44:29+03:00 |
| 193574 | Первая встреча | 1 | 213410 | Y | 2023-09-04T17:02:48+03:00 |
| 193532 | Первая встреча | 1 | 1219 | Y | 2023-09-04T16:23:56+03:00 |
| 193450 | Первая встреча | 1 | 231906 | Y | 2023-09-04T15:25:15+03:00 |
| 193264 | Первая встреча | 1 | 127656 | Y | 2023-09-04T13:25:17+03:00 |
| 193138 | Первая встреча | 1 | 222104 | Y | 2023-09-04T11:38:26+03:00 |
| 193014 | Первая встреча | 1 | 227654 | Y | 2023-09-01T16:30:30+03:00 |
| 192526 | Первая встреча | 3 | 976 | Y | 2023-08-31T14:28:39+03:00 |
| 192520 | Первая встреча | 3 | 9628 | Y | 2023-08-31T14:01:45+03:00 |
| 192440 | Первая встреча | 1 | 231892 | Y | 2023-08-31T12:56:53+03:00 |
| 192352 | Первая встреча | 1 | 223664 | Y | 2023-08-31T10:58:27+03:00 |
| 192100 | Первая встреча | 1 | 228880 | Y | 2023-08-28T11:31:39+03:00 |
| 192082 | Первая встреча | 3 | 17142 | Y | 2023-08-28T11:22:31+03:00 |
| 191788 | Первая встреча | 1 | 5230 | Y | 2023-08-24T12:49:37+03:00 |
| 191640 | Первая встреча | 1 | 225192 | Y | 2023-08-23T15:26:53+03:00 |
| 190834 | Первая встреча | 1 | 231736 | Y | 2023-08-16T16:39:51+03:00 |
| 190740 | Первая встреча | 1 | 231744 | Y | 2023-08-16T14:06:53+03:00 |
| 189808 | Первая встреча | 1 | 230616 | Y | 2023-08-14T18:53:46+03:00 |
| 189366 | Первая встреча | 1 | 231408 | Y | 2023-08-11T11:41:31+03:00 |
| 189364 | Первая встреча | 1 | 83756 | Y | 2023-08-11T11:39:21+03:00 |
| 189190 | Первая встреча | 3 | 17102 | Y | 2023-08-10T13:28:46+03:00 |
| 188918 | Первая встреча | 1 | 164090 | Y | 2023-08-08T12:42:18+03:00 |
| 188904 | Первая встреча | 1 | 231688 | Y | 2023-08-08T11:31:26+03:00 |
| 188880 | Первая встреча | 3 | 17080 | Y | 2023-08-07T22:28:40+03:00 |

**Вывод:** отдельного поля «первая/повторная» в структуре activity не обнаружено. Для METRICS-SPEC считать: первая = первая по `CREATED` activity `TYPE_ID=1` у `OWNER_ID`/deal или company; повторная = вторая и далее.

## 3. Smart-process «КП»

### entityTypeId=1106 title=КП

Статусы:

| STATUS_ID | NAME | SORT | SEMANTICS |
|---|---|---|---|
| DT1106_54:NEW | В работе | 10 | None |
| DT1106_54:CLIENT | Проверка | 20 | None |
| DT1106_54:PREPARATION | Доработка | 30 | None |
| DT1106_54:SUCCESS | Готово | 40 | S |
| DT1106_54:FAIL | Не акутально | 50 | F |

```json
{
  "items": [
    {
      "accountCurrencyId": "RUB",
      "assignedById": 2822,
      "begindate": "2026-04-08T03:00:00+03:00",
      "categoryId": 54,
      "closedate": "2026-05-04T03:00:00+03:00",
      "companyId": 0,
      "contactId": 0,
      "contactIds": [],
      "createdBy": 2818,
      "createdTime": "2026-04-08T14:03:20+03:00",
      "currencyId": "RUB",
      "entityTypeId": 1106,
      "id": 16,
      "isManualOpportunity": "N",
      "isRecurring": "N",
      "lastActivityBy": 1728,
      "lastActivityTime": "2026-04-13T19:00:00+03:00",
      "lastCommunicationCallTime": null,
      "lastCommunicationEmailTime": null,
      "lastCommunicationImolTime": null,
      "lastCommunicationTime": null,
      "lastCommunicationWebformTime": null,
      "movedBy": 2188,
      "movedTime": "2026-05-04T16:06:46+03:00",
      "mycompanyId": 15220,
      "observers": [],
      "opened": "Y",
      "opportunity": 0,
      "opportunityAccount": 0,
      "parentId2": 18270,
      "previousStageId": "DT1106_54:NEW",
      "sourceDescription": "",
      "sourceId": "1",
      "stageId": "DT1106_54:FAIL",
      "taxValue": 0,
      "taxValueAccount": 0,
      "title": "emeds.ru",
      "ufCrm44_1774430649388": 8650,
      "ufCrm44_1774430907621": 8652,
      "ufCrm44_1774430954": 256,
      "ufCrm44_1774441127": "1254",
      "ufCrm44_1774441592": 1728,
      "ufCrm44_1774443836698": 505750,
      "ufCrm44_1774445591843": "",
      "ufCrm44_1774959632": "2026-04-08T03:00:00+03:00",
      "ufCrm44_1775392910461": -1003553166106,
      "ufCrm44_1775397079": 0,
      "ufCrm44_1775402465": "",
      "updatedBy": 2188,
      "updatedTime": "2026-05-04T16:06:49+03:00",
      "utmCampaign": null,
      "utmContent": null,
      "utmMedium": null,
      "utmSource": null,
      "utmTerm": null,
      "webformId": 0,
      "xmlId": ""
    },
    {
      "accountCurrencyId": "RUB",
      "assignedById": 2822,
      "begindate": "2026-04-08T03:00:00+03:00",
      "categoryId": 54,
      "closedate": "2026-05-04T03:00:00+03:00",
      "companyId": 0,
      "contactId": 0,
      "contactIds": [],
      "createdBy": 2818,
      "createdTime": "2026-04-08T17:11:47+03:00",
      "currencyId": "RUB",
      "entityTypeId": 1106,
      "id": 18,
      "isManualOpportunity": "N",
      "isRecurring": "N",
      "lastActivityBy": 582,
      "lastActivityTime": "2026-04-14T19:00:00+03:00",
      "lastCommunicationCallTime": null,
      "lastCommunicationEmailTime": null,
      "lastCommunicationImolTime": null,
      "lastCommunicationTime": null,
      "lastCommunicationWebformTime": null,
      "movedBy": 2358,
      "movedTime": "2026-05-04T15:58:18+03:00",
      "mycompanyId": 15220,
      "observers": [],
      "opened": "Y",
      "opportunity": 0,
      "opportunityAccount": 0,
      "parentId2": 18270,
      "previousStageId": "DT1106_54:NEW",
      "sourceDescription": "",
      "sourceId": "1",
      "stageId": "DT1106_54:SUCCESS",
      "taxValue": 0,
      "taxValueAccount": 0,
      "title": "emeds.ru",
      "ufCrm44_1774430649388": 8650,
      "ufCrm44_1774430907621": 8662,
      "ufCrm44_1774430954": 582,
      "ufCrm44_1774441127": "1256",
      "ufCrm44_1774441592": 582,
      "ufCrm44_1774443836698": 505872,
      "ufCrm44_1774445591843": "",
      "ufCrm44_1774959632": "2026-04-14T03:00:00+03:00",
      "ufCrm44_1775392910461": -1003239680882,
      "ufCrm44_1775397079": 0,
      "ufCrm44_1775402465": "ORM (управление репутацией): https://pitch.com/v/orm-cekpuc",
      "updatedBy": 0,
      "updatedTime": "2026-05-04T15:58:45+03:00",
      "utmCampaign": null,
      "utmContent": null,
      "utmMedium": null,
      "utmSource": null,
      "utmTerm": null,
      "webformId": 0,
      "xmlId": ""
    },
    {
      "accountCurrencyId": "RUB",
      "assignedById": 2822,
      "begindate": "2026-04-08T03:00:00+03:00",
      "categoryId": 54,
      "closedate": "2026-04-15T03:00:00+03:00",
      "companyId": 0,
      "contactId": 0,
      "contactIds": [],
      "createdBy": 2818,
      "createdTime": "2026-04-08T20:15:44+03:00",
      "currencyId": "RUB",
      "entityTypeId": 1106,
      "id": 20,
      "isManualOpportunity": "N",
      "isRecurring": "N",
      "lastActivityBy": 2806,
      "lastActivityTime": "2026-05-18T19:00:00+03:00",
      "lastCommunicationCallTime": null,
      "lastCommunicationEmailTime": null,
      "lastCommunicationImolTime": null,
      "lastCommunicationTime": null,
      "lastCommunicationWebformTime": null,
      "movedBy": 2358,
      "movedTime": "2026-05-12T17:26:22+03:00",
      "mycompanyId": 15220,
      "observers": [],
      "opened": "Y",
      "opportunity": 0,
      "opportunityAccount": 0,
      "parentId2": 23662,
      "previousStageId": "DT1106_54:NEW",
      "sourceDescription": "",
      "sourceId": "1",
      "stageId": "DT1106_54:CLIENT",
      "taxValue": 0,
      "taxValueAccount": 0,
      "title": "kraftwayclinic.ru",
      "ufCrm44_1774430649388": 8650,
      "ufCrm44_1774430907621": 8666,
      "ufCrm44_1774430954": 470,
      "ufCrm44_1774441127": "1250",
      "ufCrm44_1774441592": 2822,
      "ufCrm44_1774443836698": 505932,
      "ufCrm44_1774445591843": "",
      "ufCrm44_1774959632": "2026-04-07T03:00:00+03:00",
      "ufCrm44_1775392910461": -1003744787347,
      "ufCrm44_1775397079": 470,
      "ufCrm44_1775402465": "",
      "updatedBy": 2806,
      "updatedTime": "2026-05-18T19:00:17+03:00",
      "utmCampaign": null,
      "utmContent": null,
      "utmMedium": null,
      "utmSource": null,
      "utmTerm": null,
      "webformId": 0,
      "xmlId": ""
    },
    {
      "accountCurrencyId": "RUB",
      "assignedById": 584,
      "begindate": "2026-04-09T03:00:00+03:00",
      "categoryId": 54,
      "closedate": "2026-04-16T03:00:00+03:00",
      "companyId": 0,
      "contactId": 0,
      "contactIds": [],
      "createdBy": 584,
      "createdTime": "2026-04-09T11:32:53+03:00",
      "currencyId": "RUB",
      "entit
…
```

**Вывод:** smart-process КП найден: `entityTypeId=1106`, categoryId=54. Для MVP «КП выслано» считать по успешной стадии `DT1106_54:SUCCESS` (`Готово`, semantics `S`).

## 4. Smart-process «Договор» / стадия сделки

### crm.type.list — договорные smart-processes

### entityTypeId=1110 title=Договор

Статусы:

| STATUS_ID | NAME | SORT | SEMANTICS |
|---|---|---|---|
| DT1110_56:NEW | Начало | 10 | None |
| DT1110_56:PREPARATION | Подготовка | 20 | None |
| DT1110_56:CLIENT | Согласование | 30 | None |
| DT1110_56:SUCCESS | Успех | 40 | S |
| DT1110_56:FAIL | Провал | 50 | F |

```json
{
  "items": [
    {
      "accountCurrencyId": "RUB",
      "assignedById": 2358,
      "begindate": "2026-04-15T03:00:00+03:00",
      "categoryId": 56,
      "closedate": "2026-04-22T03:00:00+03:00",
      "companyId": 16318,
      "contactId": 0,
      "contactIds": [],
      "createdBy": 2358,
      "createdTime": "2026-04-15T14:31:06+03:00",
      "currencyId": "RUB",
      "entityTypeId": 1110,
      "id": 2,
      "isManualOpportunity": "N",
      "isRecurring": "N",
      "lastActivityBy": 2358,
      "lastActivityTime": "2026-04-15T14:31:06+03:00",
      "lastCommunicationCallTime": null,
      "lastCommunicationEmailTime": null,
      "lastCommunicationImolTime": null,
      "lastCommunicationTime": null,
      "lastCommunicationWebformTime": null,
      "movedBy": 2358,
      "movedTime": "2026-04-15T14:31:06+03:00",
      "mycompanyId": 15220,
      "observers": [],
      "opened": "N",
      "opportunity": 0,
      "opportunityAccount": 0,
      "parentId2": null,
      "parentId31": null,
      "previousStageId": "",
      "sourceDescription": "",
      "sourceId": "1",
      "stageId": "DT1110_56:NEW",
      "taxValue": 0,
      "taxValueAccount": 0,
      "title": "Договор #2",
      "ufCrm46_1776252357": null,
      "ufCrm46_1776252459": null,
      "ufCrm46_1776771889": null,
      "ufCrm46_1776775540": null,
      "updatedBy": 2358,
      "updatedTime": "2026-04-21T15:19:10+03:00",
      "utmCampaign": null,
      "utmContent": null,
      "utmMedium": null,
      "utmSource": null,
      "utmTerm": null,
      "webformId": 0,
      "xmlId": ""
    }
  ]
}
```

### crm.dealcategory.stage.list id=10

| STAGE_ID | NAME | SORT | SEMANTICS |
|---|---|---|---|
| C10:NEW | Квалификация | 10 |  |
| C10:PREPAYMENT_INVOIC | Подготовка БРИФа | 20 |  |
| C10:EXECUTING | Подготовка КП | 30 |  |
| C10:FINAL_INVOICE | Догрев и переговоры | 40 |  |
| C10:UC_KC7195 | Подготовка договора | 50 |  |
| C10:WON | УСПЕХ | 60 |  |
| C10:LOSE | ОТВАЛ | 70 |  |
| C10:1 | ОТЛОЖЕНО | 80 |  |

**Вывод:** договор используется как smart-process `entityTypeId=1110`, categoryId=56. Для MVP «договор заключён» считать по `DT1110_56:SUCCESS` (`Успех`, semantics `S`). Альтернатива для сделок в основной воронке — `C10:WON`.

## 5. MRR / recurring

| FIELD_ID | LABEL | TYPE |
|---|---|---|
| — | — | — |

**BLOCKER:** UF-поле MRR/recurring/ежемесячного платежа в `crm.deal.fields` не найдено. Нужно добавить поле или указать существующее.

## 6. Voximplant статистика

- Поля в sample: `CALL_CATEGORY, CALL_DURATION, CALL_FAILED_CODE, CALL_FAILED_REASON, CALL_ID, CALL_LOG, CALL_RECORD_URL, CALL_START_DATE, CALL_TYPE, CALL_VOTE, COMMENT, COST, COST_CURRENCY, CRM_ACTIVITY_ID, CRM_ENTITY_ID, CRM_ENTITY_TYPE, EXTERNAL_CALL_ID, ID, PHONE_NUMBER, PORTAL_NUMBER, PORTAL_USER_ID, RECORD_DURATION, RECORD_FILE_ID, REDIAL_ATTEMPT, REST_APP_ID, REST_APP_NAME, SESSION_ID, TRANSCRIPT_ID, TRANSCRIPT_PENDING`

```json
[
  {
    "CALL_CATEGORY": "external",
    "CALL_DURATION": "0",
    "CALL_FAILED_CODE": "603-S",
    "CALL_FAILED_REASON": "Decline self",
    "CALL_ID": "33FE852BE66C3F84.1778652312.21372295",
    "CALL_LOG": "https://storage-gw-ru-02.voximplant.com/voximplant-logs/2026/05/13/MDQ5N2I4NjdmYmQ3M2JlOGM2MjZlNGUyNDk0NGMyMDUvaHR0cDovL3d3dy1ydS0zMS0xMzQudm94aW1wbGFudC5jb206ODA4MC9sb2dzLzIwMjYvMDUvMTMvMDYwNTEyX0Y4NUFCQTFGMzM2NkYyNzIuMTc3ODY1MjMxMi4yMTM3MjI5Nl8xODUuMTY0LjE0OC4xMzQubG9n?sessionid=7680442748",
    "CALL_RECORD_URL": "",
    "CALL_START_DATE": "2026-05-13T09:05:13+03:00",
    "CALL_TYPE": "1",
    "CALL_VOTE": null,
    "COMMENT": null,
    "COST": "0.0000",
    "COST_CURRENCY": "RUR",
    "CRM_ACTIVITY_ID": "435798",
    "CRM_ENTITY_ID": "26070",
    "CRM_ENTITY_TYPE": "CONTACT",
    "EXTERNAL_CALL_ID": null,
    "ID": "282670",
    "PHONE_NUMBER": "79260360101",
    "PORTAL_NUMBER": "74993255849",
    "PORTAL_USER_ID": "2772",
    "RECORD_DURATION": null,
    "RECORD_FILE_ID": null,
    "REDIAL_ATTEMPT": null,
    "REST_APP_ID": null,
    "REST_APP_NAME": null,
    "SESSION_ID": "7680442748",
    "TRANSCRIPT_ID": null,
    "TRANSCRIPT_PENDING": "N"
  },
  {
    "CALL_CATEGORY": "external",
    "CALL_DURATION": "189",
    "CALL_FAILED_CODE": "200",
    "CALL_FAILED_REASON": "Success call",
    "CALL_ID": "6BBC03ABEAD21F82.1778652356.25276842",
    "CALL_LOG": "https://storage-gw-ru-02.voximplant.com/voximplant-logs/2026/05/13/YzVlYjM3N2ZhYjEzZmZmZWFjNDE1MzJhNzVkMmZhN2EvaHR0cDovL3d3dy1ydS0yMC0xMS52b3hpbXBsYW50LmNvbTo4MDgwL2xvZ3MvMjAyNi8wNS8xMy8wNjA1NTZfMTBBMkE5RjVDNEExRDhBMy4xNzc4NjUyMzU2LjI1Mjc2ODQzXzE4NS4xNjQuMTQ5LjExLmxvZw--?sessionid=7680446164",
    "CALL_RECORD_URL": "https://storage-gw-ru-02.voximplant.com/voximplant-records/2026/05/13/M2M3YmU3YzljNjFhOThiZDg5MTMxZDFlNjQ4ZTQ1OGYvaHR0cDovL3d3dy1ydS0yMC0xMS52b3hpbXBsYW50LmNvbTo4MDgwL3JlY29yZHMvMjAyNi8wNS8xMy81NDQ2MDMyMDkyMUE1QjMyLjE3Nzg2NTIzNTguMjUyNzcxMDcubXAz.mp3?record_id=30332316544",
    "CALL_START_DATE": "2026-05-13T09:05:56+03:00",
    "CALL_TYPE": "1",
    "CALL_VOTE": null,
    "COMMENT": null,
    "COST": "8.1008",
    "COST_CURRENCY": "RUR",
    "CRM_ACTIVITY_ID": "435800",
    "CRM_ENTITY_ID": "18866",
    "CRM_ENTITY_TYPE": "COMPANY",
    "EXTERNAL_CALL_ID": null,
    "ID": "282672",
    "PHONE_NUMBER": "89581110707",
    "PORTAL_NUMBER": "74993255849",
    "PORTAL_USER_ID": "2772",
    "RECORD_DURATION": "188",
    "RECORD_FILE_ID": 770074,
    "REDIAL_ATTEMPT": null,
    "REST_APP_ID": null,
    "REST_APP_NAME": null,
    "SESSION_ID": "7680446164",
    "TRANSCRIPT_ID": "8500",
    "TRANSCRIPT_PENDING": "N"
  },
  {
    "CALL_CATEGORY": "external",
    "CALL_DURATION": "0",
    "CALL_FAILED_CODE": "603-S",
    "CALL_FAILED_REASON": "Decline self",
    "CALL_ID": "51E331EB14DEB86D.1778652684.21358414",
    "CALL_LOG": "https://storage-gw-ru-02.voximplant.com/voximplant-logs/2026/05/13/YjJkM2FlMTk4YzVmMzNkZWJjOWEwYTVjMDg3MGEyNGMvaHR0cDovL3d3dy1ydS0zMC0xMzMudm94aW1wbGFudC5jb206ODA4MC9sb2dzLzIwMjYvMDUvMTMvMDYxMTI0X0YyRjBERTc0QzY3RDkxMEYuMTc3ODY1MjY4NC4yMTM1ODQxNV8xODUuMTY0LjE0OC4xMzMubG9n?sessionid=7680493268",
    "CALL_RECORD_URL": "",
    "CALL_START_DATE": "2026-05-13T09:11:25+03:00",
    "CALL_TYPE": "1",
    "CALL_VOTE": null,
    "COMMENT": null,
    "COST": "0.0000",
    "COST_CURRENCY": "RUR",
    "CRM_ACTIVITY_ID": "435802",
    "CRM_ENTITY_ID": "11192",
    "CRM_ENTITY_TYPE": "CONTACT",
    "EXTERNAL_CALL_ID": null,
    "ID": "282674",
    "PHONE_NUMBER": "+79243390079",
    "PORTAL_NUMBER": "78182464103",
    "PORTAL_USER_ID": "2832",
    "RECORD_DURATION": null,
    "RECORD_FILE_ID": null,
    "REDIAL_ATTEMPT": null,
    "REST_APP_ID": null,
    "REST_APP_NAME": null,
    "SESSION_ID": "7680493268",
    "TRANSCRIPT_ID": null,
    "TRANSCRIPT_PENDING": "N"
  },
  {
    "CALL_CATEGORY": "external",
    "CALL_DURATION": "313",
    "CALL_FAILED_CODE": "200",
    "CALL_FAILED_REASON": "Success call",
    "CALL_ID": "83E80DFBA781D790.1778652877.14449678",
    "CALL_LOG": "https://storage-gw-ru-02.voximplant.com/voximplant-logs/2026/05/13/YzZkMzAyNjhhN2I3OWI0Y2Y1YTliODJmNjJhZTM2MTYvaHR0cDovL3d3dy1ydS0yMy0xNy52b3hpbXBsYW50LmNvbTo4MDgwL2xvZ3MvMjAyNi8wNS8xMy8wNjE0MzdfMzYxODQ1MTcwOThCMjlEQS4xNzc4NjUyODc3LjE0NDQ5Njc5XzE4NS4xNjQuMTQ5LjE3LmxvZw--?sessionid=7680529564",
    "CALL_RECORD_URL": "https://storage-gw-ru-02.voximplant.com/voximplant-records/2026/05/13/ODkyZWI1NmNkODk3MDY0MDVmZTZkYjAxYmY0MTAzOTYvaHR0cDovL3d3dy1ydS0yMy0xNy52b3hpbXBsYW50LmNvbTo4MDgwL3JlY29yZHMvMjAyNi8wNS8xMy8xNzczRjI5Q0RGNzIzNkY0LjE3Nzg2NTI4ODguMTQ0NTAxOTEubXAz.mp3?record_id=30333750164",
    "CALL_START_DATE": "2026-05-13T09:14:38+03:00",
    "CALL_TYPE": "1",
    "CALL_VOTE": null,
    "COMMENT": null,
    "COST": "12.1512",
    "COST_CURRENCY": "RUR",
    "CRM_ACTIVITY_ID": "435804",
    "CRM_ENTITY_ID": "72152",
    "CRM_ENTITY_TYPE": "CONTACT",
    "EXTERNAL_CALL_ID": null,
    "ID": "282676",
    "PHONE_NUMBER": "+79147219440",
    "PORTAL_NUMBER": "78182464103",
    "PORTAL_USER_ID": "2832",
    "RECORD_DURATION": "312",
    "RECORD_FILE_ID": 770076,
    "REDIAL_ATTEMPT": null,
    "REST_APP_ID": null,
    "REST_APP_NAME": null,
    "SESSION_ID": "7680529564",
    "TRANSCRIPT_ID": "8502",
    "TRANSCRIPT_PENDING": "N"
  },
  {
    "CALL_CATEGORY": "external",
    "CALL_DURATION": "66",
    "CALL_FAILED_CODE": "200",
    "CALL_FAILED_REASON": "Success call",
    "CALL_ID": "2C1E44AEF40664D2.1778653263.21429069",
    "CALL_LOG": "https://storage-gw-ru-02.voximplant.com/voximplant-logs/2026/05/13/MzgyMWNhZTY4YzlkOWMwNWMwMjE5YzBiMDA4YTBiMDYvaHR0cDovL3d3dy1ydS0zMS0xMzQudm94aW1wbGFudC5jb206ODA4MC9sb2dzLzIwMjYvMDUvMTMvMDYyMTAzX0UxNkJEQjE5MzZBNUM3OEUuMTc3ODY1MzI2My4yMTQyOTA3MF8xODUuMTY0LjE0OC4xMzQubG9n?sessionid=7680558362",
    "CALL_RECORD_URL": "https://storage-gw-ru-02.voximplant.com/voximplant-records/2026/05/13/OTc3YjMxNjY2YjZkYjcwODBmMDJmYzFhNmIyZDBiMWEvaHR0cDovL3d3dy1ydS0zMS0xMzQudm94aW1wbGFudC5jb206ODA4MC9yZWNvcmRzLzIwMjYvMDUvMTMvRDB
…
```

**Решение:** звонок 60с+/120с+ считаем по `CALL_DURATION >= X` (общая длительность, без talk-time). `CALL_TYPE` присутствует; используем 1=исходящий, 2=входящий, 3=обратный.

## 7. ID сотрудников

### Запрошенные имена из скринов

| ID | NAME LAST_NAME | WORK_POSITION | ACTIVE | ROLE_HINT |
|---|---|---|---|---|
| — | — | — | — | — |

Не найдено по точному NAME/LAST_NAME:

- Шатура Давид через NAME=Давид LAST_NAME=Шатура
- Клетенков Антон через NAME=Антон LAST_NAME=Клетенков
- Шестаков Даниил через NAME=Даниил LAST_NAME=Шестаков
- Савич В. через NAME=Виктор LAST_NAME=Савич
- Савич В. через NAME=Владимир LAST_NAME=Савич
- Кашкаров Д. через NAME=Дмитрий LAST_NAME=Кашкаров
- Кашкаров Д. через NAME=Денис LAST_NAME=Кашкаров

### Активные кандидаты по должности

| ID | NAME LAST_NAME | WORK_POSITION | ACTIVE | ROLE_HINT |
|---|---|---|---|---|
| 2188 | Евгения Гордиенко | РОП | True | МОП |
| 2772 | Дарья Исаева | Телемаркетолог | True | ТМ |
| 2806 | Елизавета Деговцова | Менеджер по продажам | True | МОП |
| 2832 | Аркадий Вострецов | Телемаркетолог | True | ТМ |
| 2846 | Егор Семенихин | Менеджер по продажам | True | МОП |

**Вывод:** имена из скринов, вероятно, устарели или заведены иначе. Для Phase 1 config заполнен активными кандидатами по должности: ТМ — Дарья Исаева, Аркадий Вострецов; МОП — Евгения Гордиенко, Елизавета Деговцова, Егор Семенихин. Перед Phase 2 пользователь должен подтвердить финальный список.

## Raw errors

