# Runbook: Happ VPN (MSK)

## Предпосылки
- Заполнен файл `infra/happ-vpn.env` (на основе `infra/happ-vpn.env.example`).
- Доступ к серверам только по SSH-ключам.
- Все команды запускать из корня `Инженер`.

## Команды
1. Аудит инфраструктуры:
```bash
make vpn.audit
```

2. Деплой primary+reserve+subscription:
```bash
make vpn.deploy
```

3. Верификация (одной командой):
```bash
make vpn.verify
```

4. Безопасный откат:
```bash
make vpn.rollback
```

## Ротация
1. Сгенерировать новые ключи/UUID вне git.
2. Обновить секреты в `infra/happ-vpn.env` и secret files на сервере.
3. Перегенерировать subscription через оркестратор:
```bash
make vpn.deploy
```
4. Повторный деплой и verify:
```bash
make vpn.deploy
make vpn.verify
```

## Единый daily_ops в 09:30 MSK
```bash
DRY_RUN=0 make openclaw.daily-ops
```
Что делает:
1. `checks/vpn_verify.sh`
2. `checks/vpn_smoke_happ.sh`
3. `checks/morning_health_report.sh`
4. `checks/context_contract_verify.sh`
5. `checks/instruction_conflicts.sh`
6. `scripts/verify_integrations.sh`
7. Отправка краткого статуса в Telegram (если заданы токены), при проблемах — инцидент в `reports/incidents/`.

Формат итога: `ОК / есть проблемы` + ссылка на единый отчет `reports/daily_ops_*_MSK.txt`.

## Подготовка на следующую неделю
```bash
make openclaw.next-week-prep
```
Результат: файл `reports/next_week_prep_*_MSK.md` с задачами подготовки и one-click командами.

## Контур аналитики и handoff
```bash
make openclaw.ops-intelligence
make openclaw.session-handoff
```

## Rollback dry-run
```bash
DRY_RUN=1 make vpn.rollback
```
