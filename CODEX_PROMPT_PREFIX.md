# Codex Prompt Prefix — Belberry CRM Enrichment

Перед любыми действиями прочитай:

```text
~/work-crm-enrich/WORKSPACE.md
```

Всё canonical setup внутри. Python ТОЛЬКО через venv.
Base ветка для PR — `main`.

## Шаблон задачи

```md
ЗАДАЧА: <одной фразой что нужно сделать>

КОНТЕКСТ:
- <что уже сделано / какие баги найдены / какой свежий state>

ЧТО ИМЕННО:
1. <шаг 1, конкретно>
2. <шаг 2, конкретно>
3. <шаг 3>

ВЫХОД:
- Финальный отчёт markdown-блоком:
  - что закоммитил, SHA
  - какие тесты прошли, `N passed`
  - `git status`
  - ссылка на созданный PR
  - `git log -3`
- Если что-то не получилось: `BLOCKED: <причина>` и остановиться.
```

## Пример

```md
Перед любыми действиями прочитай:
  ~/work-crm-enrich/WORKSPACE.md
Всё canonical setup внутри. Python ТОЛЬКО через venv. Base ветка для PR — main.

ЗАДАЧА: пофиксить false-positive по ликвидации компании в sync_deals.py

КОНТЕКСТ:
- Codex ранее обнаружил баг: общий маркер "ликвидировано" срабатывает на нерелевантный текст со страницы поиска Rusprofile
- В worktree уже есть uncommitted правки в sync_deals.py + test_sync_deals.py

ЧТО ИМЕННО:
1. Закончи правку, прогони pytest на test_sync_deals.py — должен быть зелёный
2. Создай ветку fix/sync-deals-liquidation-false-positive от свежего main
3. Commit + push + PR + squash merge — по workflow из WORKSPACE.md
4. После merge — pull main

ВЫХОД:
- Финальный отчёт с SHA коммита, PR URL, `N passed` из pytest, `git status`, `git log -3`
```

## Принципы

- Prefix в начало каждой сессии, чтобы Codex сразу знал canonical paths.
- Один thread = одна логическая задача.
- При context compression повторять prefix.
- Каждая фича = новая ветка от свежего `main`.
- Финальный отчёт Codex должен быть пригоден как prompt/context для ревью.
