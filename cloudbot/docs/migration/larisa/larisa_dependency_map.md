# Larisa Dependency Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only dependency map. Этот документ не меняет `agents/larisa_ivanovna`, imports, runtime, env или deploy.

## 1. Current active path

```text
agents/larisa_ivanovna
```

Target placeholder exists, but active code has not moved:

```text
apps/larisa_ivanovna
```

## 2. Confirmed external entrypoints

| Entrypoint | Current command/path |
| --- | --- |
| Daily brief workflow | `python3 -m agents.larisa_ivanovna --command get_day_brief` |
| Evening review workflow | `python3 -m agents.larisa_ivanovna --command get_evening_review` |
| Content topics workflow | `python3 -m agents.larisa_ivanovna --command get_content_topics` |
| Midday replan workflow | `python3 -m agents.larisa_ivanovna --command get_midday_replan` |
| Send note helper | imports `SharedTelegramRouteProvider` |

## 3. Cloudbot workflow dependencies

Confirmed `cloudbot/workflows/*` imports:

```text
cloudbot/workflows/larisa_runtime.py -> agents.larisa_ivanovna.*
cloudbot/workflows/day_briefing.py -> larisa_runtime
cloudbot/workflows/tasks_summary.py -> larisa_runtime
cloudbot/workflows/meetings_summary.py -> larisa_runtime
cloudbot/workflows/larisa_weather.py -> larisa_runtime
cloudbot/workflows/larisa_search.py -> larisa_runtime
cloudbot/workflows/larisa_content_topics.py -> larisa_runtime
cloudbot/workflows/larisa_content_post.py -> larisa_runtime
cloudbot/workflows/larisa_plan_day.py -> larisa_runtime
```

## 4. Internal components

Active internal areas:

```text
commands/
config.py
formatters/
policy.py
providers/
schemas/
timezone.py
workflows/
agent.py
```

## 5. Tests locking current path

Current tests import:

```text
agents.larisa_ivanovna.agent
agents.larisa_ivanovna.config
agents.larisa_ivanovna.providers.*
agents.larisa_ivanovna.schemas.*
agents.larisa_ivanovna.workflows.*
cloudbot.workflows.larisa_runtime
```

## 6. Migration risk

Moving Larisa code is high-risk because:

- CLI entrypoints use `python3 -m agents.larisa_ivanovna`;
- `cloudbot/workflows/larisa_runtime.py` imports old paths;
- tests lock old paths;
- workflows and route mapping depend on Larisa workflow names;
- Telegram delivery/chat routing must not change.

## 7. Verdict

```text
Larisa code move blocked
dependency map completed
next safe step: Larisa runtime entrypoint map
```
