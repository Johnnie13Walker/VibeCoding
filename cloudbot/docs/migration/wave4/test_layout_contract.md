# Test Layout Contract

Дата фиксации: 2026-04-28 МСК.

Статус: migration contract. Этот документ фиксирует правила будущей раскладки тестов. Он не меняет production code, runtime, env, cron, systemd, docker или deploy scripts.

## 1. Цель

Цель test layout migration - отделить быстрые локальные проверки от integration/smoke проверок, чтобы будущая structural migration шла через понятный цикл:

```text
small move -> local test -> status check -> next move
```

## 2. Target layout

```text
tests/
  unit/
  integration/
  smoke/
  fixtures/
```

## 3. Unit tests

`tests/unit/` предназначен для тестов, которые:

- не требуют live env;
- не требуют server access;
- не требуют Telegram token/chat;
- не требуют Bitrix live API;
- не требуют OpenAI API;
- не требуют WHOOP/Todo live access;
- используют fixtures, fakes или mocks;
- могут выполняться локально через `python3 -m unittest discover`.

Текущие migrated unit tests:

```text
tests/unit/test_search_provider.py
tests/unit/test_bitrix_app_auth.py
tests/unit/test_bitrix_sales_adapter.py
```

Команда проверки:

```bash
python3 -m unittest discover -s tests/unit
```

## 4. Integration tests

`tests/integration/` предназначен для тестов, которые проверяют совместную работу нескольких локальных модулей, но не должны трогать live runtime без отдельного approval.

Кандидаты требуют отдельного review:

```text
tests/test_sales_dispatch_contract.py
tests/test_larisa_search.py
tests/test_system_health.py
```

Не переносить автоматически.

## 5. Smoke tests

`tests/smoke/` предназначен для owner-safe smoke checks после будущих approved moves.

Smoke checks должны быть явно разделены:

- Larisa smoke;
- Lev/Sales smoke;
- shared-core smoke;
- config/env contract smoke.

Запрещено добавлять smoke checks, которые требуют live secrets/server/runtime, без отдельного owner approval.

## 6. Tests пока вне migration scope

Следующие тесты нельзя переносить автоматически:

```text
tests/test_larisa_agent.py
tests/test_lev_petrovich_runtime.py
tests/test_sales_dispatch_contract.py
tests/test_system_health.py
tests/unit/test_finansist_agent.py
tests/test_larisa_search.py
```

Причины:

- связаны с Larisa или Lev/Sales runtime behavior;
- могут проверять report/delivery/dispatch contracts;
- могут быть связаны с finance contour;
- требуют отдельного dependency review.

## 7. Fixture policy

`tests/fixtures/` остается на месте.

Не переносить fixtures в рамках Wave 4 без отдельного review, потому что несколько тестов могут ссылаться на `Path(__file__)` или относительные пути.

## 8. No-touch policy

В рамках test layout migration запрещено:

- менять production code;
- менять imports в `agents/*`;
- менять imports в `cloudbot/*`;
- менять runtime/env/cron/systemd/docker;
- менять deploy/rollback/verify scripts;
- менять `agents/sales_agent`;
- переносить finance/iOS/HAPP/VPN/subscription контуры;
- запускать проверки, требующие live secrets/server access.

## 9. Verification gate

После каждого test move обязательно выполнить:

```bash
python3 -m unittest discover -s tests/unit -p '<moved_test_file>'
git status --short tests
```

После группы unit moves обязательно выполнить:

```bash
python3 -m unittest discover -s tests/unit
```

Переход к следующему шагу разрешен только если:

- все migrated unit tests проходят;
- изменены только утвержденные test paths и docs;
- нет изменений runtime/deploy/env зон;
- нет изменений `agents/sales_agent`.

## 10. Current verification target

Текущий обязательный target:

```bash
python3 -m unittest discover -s tests/unit
```

Ожидаемый результат:

```text
OK
```
