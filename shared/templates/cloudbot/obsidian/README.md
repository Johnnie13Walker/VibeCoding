# Obsidian provider/skills — референсная реализация

Каталог содержит референсные шаблоны для серверного runtime Cloudbot.
Эти файлы **не подключены к работающему боту** в данном репозитории —
runtime Cloudbot живёт на сервере, а здесь хранится только проектный
и операционный контур.

Шаблоны соответствуют контракту `shared/docs/integrations/obsidian_vault.md`
и предназначены для портирования в серверный runtime после
подтверждения путей и авторизации владельцем.

## Состав

- `obsidian_provider.py` — provider: vault + git-sync.
- `obsidian_save_note.py` — skill: сохранить заметку в `Inbox/`.
- `obsidian_append_daily.py` — skill: добавить блок в дневную заметку.
- `obsidian_search.py` — skill: поиск по vault.
- `obsidian_create_task.py` — skill: создать задачу в `Tasks/`.

## Целевые пути в runtime

```text
cloudbot/providers/obsidian_provider.py
cloudbot/skills/obsidian_save_note.py
cloudbot/skills/obsidian_append_daily.py
cloudbot/skills/obsidian_search.py
cloudbot/skills/obsidian_create_task.py
```

## Зависимости рантайма

Шаблоны написаны на Python 3.10+, без внешних библиотек кроме стандартной.

Для git-операций используется системный `git` — серверу нужно иметь
склонированный private repo в `OBSIDIAN_VAULT_PATH` с настроенным
deploy key или SSH key для push/pull.

## Безопасность

- Vault не должен содержать `.env`, токены, ключи (см. контракт).
- Все пути, передаваемые наружу, нормализуются через `_safe_join`,
  чтобы исключить выход за пределы vault.
- Все git-операции обёрнуты файловым lock, чтобы параллельные запросы
  не конфликтовали при `git push`.

## Что нужно сделать при портировании

1. Скопировать файлы в фактические пути runtime.
2. Согласовать импорты с существующими провайдерами Cloudbot
   (logging, error reporting, конфиг-loader).
3. Зарегистрировать provider и skills в bootstrap Cloudbot
   (по аналогии с `whoop_provider`, `bitrix_provider`).
4. Прогнать `cloudbot/skills/obsidian_*` на тестовых заметках
   до подключения к Telegram-командам.
