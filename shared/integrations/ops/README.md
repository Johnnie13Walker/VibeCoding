# Ops scripts

Операционные скрипты для работы с production-сервером Cloudbot.

## Состав

- `ssh_happ.sh` — SSH-шорткат к primary/reserve хостам через alias из `~/.ssh/config`.

## Зависимости

`ssh_happ.sh` ищет конфиг по относительному пути `../infra/remote-ops.env` (то есть `shared/integrations/infra/remote-ops.env`).

Реальный `remote-ops.env` **не коммитится** (есть в `.gitignore`). Шаблон — `shared/integrations/infra/remote-ops.env.example`.

## Первичная настройка

```bash
cp shared/integrations/infra/remote-ops.env.example shared/integrations/infra/remote-ops.env
$EDITOR shared/integrations/infra/remote-ops.env
```

Заполнить:

- `PRIMARY_HOST` — host или alias из `~/.ssh/config`;
- `RESERVE_HOST` — резервный, если есть;
- `SSH_USER`, `SSH_PORT`, `SSH_KEY_PATH` — параметры подключения.

## Использование

```bash
shared/integrations/ops/ssh_happ.sh primary           # интерактивная сессия
shared/integrations/ops/ssh_happ.sh primary "uptime"  # одна команда
shared/integrations/ops/ssh_happ.sh reserve "..."     # на резервный
```

## Безопасность

- SSH-ключи и реальный конфиг хранить только локально в `~/.ssh/` и `shared/integrations/infra/remote-ops.env`.
- В репозиторий не должны попадать ни сами ключи, ни host-aliases с реальными IP/доменами.
- Любой production-write через эти скрипты требует явного подтверждения владельца.
