# Infra pending review — 2026-04-29 МСК

## Статус

Infra/orchestrator dirty-state не принят в текущую безопасную миграционную линию.

Причина: изменения затрагивают deploy, runtime, cron, OpenClaw update, remote todo remediation, docker/container операции и server-only контуры.

## Файлы в pending review

- `infra/orchestrator/run_workflow.sh`
- `infra/orchestrator/workflows/cloudbot_github_migrate.sh`
- `infra/orchestrator/workflows/cloudbot_repo_setup.sh`
- `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- `infra/orchestrator/workflows/daily_ops.sh`
- `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- `infra/orchestrator/workflows/larisa_evening_review.sh`
- `infra/orchestrator/workflows/larisa_midday_replan.sh`
- `infra/orchestrator/workflows/openclaw_gateway_repair.sh`
- `infra/orchestrator/workflows/openclaw_healthcheck_schedule.sh`
- `infra/orchestrator/workflows/openclaw_update.sh`
- `infra/orchestrator/workflows/sales_agent_deploy.sh`
- `infra/orchestrator/workflows/todo-digest-remediate.apply.remote.sh`
- `infra/orchestrator/workflows/todo-digest-remediate.smoke.remote.sh`
- `infra/orchestrator/workflows/todo-digest-repair.sh`
- `infra/orchestrator/workflows/todo_digest_schedule.sh`

## Предварительная классификация

| Зона | Риск | Решение |
| --- | --- | --- |
| `run_workflow.sh` | меняет список workflow и default env | investigate first |
| `larisa_agent_deploy.sh` | меняет production cron, runtime release и system runner | runtime approval required |
| `sales_agent_deploy.sh` | меняет Sales runtime env/deploy output | runtime approval required |
| `openclaw_healthcheck_schedule.sh` | меняет OpenClaw cron delivery/message contract | runtime approval required |
| `openclaw_update.sh` | docker/container/runtime mutation | runtime approval required |
| `openclaw_gateway_repair.sh` | меняет runtime search provider repair behavior | runtime approval required |
| `todo-digest-*` | меняет `/root/.openclaw/workspace/todo-integration`, cron и container behavior | server-only dependency map required |
| `daily_ops.sh` | меняет operational checks | investigate first |
| `cloudbot_*` workflows | GitHub/runtime setup/verify | investigate first |
| `larisa_midday_replan.sh`, `larisa_evening_review.sh` | локальные workflow wrappers, но завязаны на remote todo snapshot | investigate first |

## Что уже проверено

- `bash -n` по всем изменённым shell-файлам из `infra/orchestrator` проходит.
- Это только syntax check, не runtime approval.

## Что запрещено до approval

- деплой;
- перезапуск сервисов;
- применение cron/systemd/docker изменений;
- изменение `/opt`, `/etc`, `/root`, `/home/ops`;
- изменение runtime pointers;
- принятие deploy/rollback/verify logic одним общим commit.

## Следующий правильный шаг

Разбить infra pending review на отдельные runtime tracks:

1. Larisa deploy/runtime track.
2. Sales deploy/runtime track.
3. OpenClaw schedule/status report track.
4. Todo digest server-only track.
5. OpenClaw search/update repair track.
6. Local-only workflow wrapper track.

Каждый track должен иметь отдельный approval, smoke checklist и rollback expectation.
