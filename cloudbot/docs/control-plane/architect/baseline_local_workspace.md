# Baseline local workspace

Дата фиксации: 2026-04-23 11:34:58 МСК  
Режим: read-only inventory. Runtime, code, env, cron, systemd, docker, symlink и deploy не менялись.

## 1. Canonical local paths

| Path | Status | Role | Source of truth |
|---|---|---|---|
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | exists | основной инженерный repo Cloudbot/OpenClo | yes |
| `/Users/pro2kuror/Desktop/architect` | exists | docs/control-plane repo | yes, для docs/control-plane |
| `/Users/pro2kuror/Desktop/Cloudbot` | exists | symlink workspace wrapper | no |
| `/Users/pro2kuror/Desktop/tools` | exists | external Paperclip workspace | no |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | exists | legacy sales/knowledge contour | no |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | exists | standalone WHOOP sandbox | unclear |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | exists | experimental JS OpenClaw extensions | no |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | exists | restored archive workspace | no |

## 2. Cloudbot symlink wrapper

`/Users/pro2kuror/Desktop/Cloudbot` is not source of truth. It contains symlinks:

```text
/Users/pro2kuror/Desktop/Cloudbot/architect -> /Users/pro2kuror/Desktop/architect
/Users/pro2kuror/Desktop/Cloudbot/engineer -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer
/Users/pro2kuror/Desktop/Cloudbot/paperclip -> /Users/pro2kuror/Desktop/tools/paperclip
```

Evidence from `/Users/pro2kuror/Desktop/Cloudbot/README.md`:

- `architect` is control-plane/docs.
- `engineer` is the main engineering git contour.
- `paperclip` is an external orchestration project and not source of truth for Cloudbot.
- The README explicitly says current system is tied to absolute paths:
  - `/Users/pro2kuror/Desktop/architect`
  - `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`

## 3. Local top-level structure snapshot

Relevant directories observed:

```text
Cloudbot/
Cloudbot/bin/
OpenClo/
OpenClo/archive/restored-workspace/
OpenClo/incubator/openclaw-extensions/
OpenClo/projects/commercial-director/
OpenClo/projects/engineer/
OpenClo/projects/whoop/
architect/
architect/docs/
architect/scripts/
architect/tmp/
tools/
tools/paperclip/
```

## 4. Sensitive local files observed by path only

No secret values were read or printed.

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.example
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations.example
```

Known from prior audit:

```text
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/.env.integrations
-> /Users/pro2kuror/.config/openclo/assistant/.env.integrations
```

This private env symlink is not source code and must not be migrated into git.

## 5. Local baseline conclusion

- Application source of truth: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
- Documentation/control-plane source of truth: `/Users/pro2kuror/Desktop/architect`.
- `/Users/pro2kuror/Desktop/Cloudbot` is only a wrapper and must not be treated as canonical source.
- External tool contour: `/Users/pro2kuror/Desktop/tools/paperclip`.
- Legacy/experimental/archive contours are present under `/Users/pro2kuror/Desktop/OpenClo`.

