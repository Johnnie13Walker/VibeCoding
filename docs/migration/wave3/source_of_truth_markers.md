# OpenCloud Source of Truth Markers

## 1. Canonical code source

Canonical working repository for application code:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer
```

Все structural changes, migration work, architecture work должны идти отсюда.

Работа через другие локальные обертки запрещена.

---

## 2. Cloudbot wrapper rule

```text
/Users/pro2kuror/Desktop/Cloudbot
```

НЕ является source of truth.

Это compatibility wrapper / symlink layer.

Используется только как legacy navigation layer.

Нельзя:

- считать его главным repo
- делать structural migration через него
- использовать его как canonical working directory

---

## 3. Docs / control-plane rule

```text
/Users/pro2kuror/Desktop/architect
```

Это docs / control-plane контур.

Используется для:

- архитектурных решений
- migration planning
- ADR
- runbooks
- decision packages

Не является runtime source.

---

## 4. sales_agent compatibility rule

```text
agents/sales_agent
```

НЕ является legacy для удаления.

Это temporary compatibility layer.

Обязательные правила:

- не удалять
- не retire
- не переносить без отдельного owner approval
- Lev/Sales runtime должен оставаться совместимым с ним

Retirement возможен только отдельным approved track позже.

Не внутри текущего Wave 3.

---

## 5. Runtime no-touch rule

Следующие зоны запрещены для structural migration:

- `/opt/cloudbot-runtime/larisa/current`
- `/opt/cloudbot-runtime/current`
- `/opt/openclaw`
- `/etc/openclaw`
- `/etc/cron.d/*`
- `/etc/systemd/*`
- docker runtime
- live env files
- deploy/rollback/verify scripts

Любые изменения там - только отдельным runtime approval.

Не в рамках Wave 3.

---

## 6. Excluded contours

Не входят в текущую migration scope:

- finance contour
- `ios/FormaNutrition`
- HAPP/VPN
- subscription cleanup
- server-only integrations
- Larisa feature changes
- Sales/Lev feature changes
- shared-core functional changes
- infra runtime/deploy changes

Эти зоны идут отдельными треками.

Не смешивать с Wave 3.

---

## 7. Working principle

Правило:

```text
minimum safe change first
```

Сначала:

```text
documentation and boundaries
```

Потом:

```text
structural preparation
```

Потом:

```text
controlled migration
```

Никогда:

```text
runtime-first changes
```
