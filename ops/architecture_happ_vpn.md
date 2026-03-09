# Архитектура Happ VPN (минимально-сложная)

## Выбранный стек
- Data-plane: `sing-box` (VLESS + Reality) на каждой ноде.
- Subscription endpoint: статический `happ_subscription.txt`, отдаваемый через HTTPS.
- Оркестрация: локальный workflow-раннер `infra/orchestrator/run_workflow.sh`.

Почему так:
1. Минимум компонентов и простая эксплуатация.
2. Нативная поддержка multi-node через подписку Happ.
3. Быстрый rollback за счет конфиг-бэкапов на нодах.

## Топология
- Primary node: обслуживает основной трафик.
- Reserve node: всегда поднята, включена в подписку.
- Subscription endpoint: единая точка выдачи конфигов Happ.

## Security baseline
1. SSH только по ключам (`BatchMode`, пароль отключается на хосте).
2. UFW: разрешены только `22/tcp` и VPN/TLS порт.
3. `fail2ban` включен и автозапуск через systemd.
4. Секреты только во внешнем env/secret файле.
5. systemd hardening для `sing-box.service`.
