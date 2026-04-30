# Runbook: OpenClaw Security Profile (MSK)

## Цель
Зафиксировать для health-check единый профиль эксплуатации, чтобы отчеты не запрашивали вводные каждый раз.

## Файл профиля
- Шаблон в репозитории: `infra/openclaw-security-profile.env.example`
- Боевой путь на хосте: `/opt/openclaw/.env.security_profile`

## Что задается в профиле
- профиль риска (`RISK_PROFILE`)
- канал доступа к хосту (`ACCESS_MODE`)
- запрет/разрешение публичной панели (`PUBLIC_DASHBOARD_ALLOWED`)
- статус шифрования диска (`DISK_ENCRYPTION_STATUS`)
- требования к бэкапам (`BACKUP_REQUIRED`, `BACKUP_MAX_AGE_HOURS`, `BACKUP_PATHS`)
- обязательные ежедневные задачи (`SCHEDULE_SECURITY_AUDIT_DEEP`, `SCHEDULE_UPDATE_STATUS`)

## Применение
1. Скопировать шаблон на хост:
```bash
cp infra/openclaw-security-profile.env.example /opt/openclaw/.env.security_profile
```
2. Заполнить значения под прод.
3. Перезапустить утренний check (или дождаться следующего прогона).

## Через оркестратор
```bash
cd "/Users/pro2kuror/Desktop/OpenClo/projects/engineer"
DRY_RUN=1 make openclaw.security-profile
# после проверки:
DRY_RUN=0 make openclaw.security-profile
```

## Результат в отчете
`reports/host-security-check.sh.remote` включает блок `Профиль эксплуатации` и сверяет критичные условия:
- публичный bind gateway против политики профиля
- статус шифрования диска
- свежесть резервных копий
