# AGENTS.md

## Режим работы: только через оркестратор
1) Все операции выполняются через orchestrator workflow.
2) Прямые ручные боевые вызовы команд запрещены, если есть соответствующий workflow.
3) Если workflow отсутствует, его нужно создать и только затем запускать задачу.
4) Время: Europe/Moscow. Язык: русский.

## Serena MCP

Always use the Serena MCP server for codebase navigation, symbol search, semantic edits, onboarding, and project understanding.

At the start of every new session:
1. Call serena.activate_project
2. Call serena.check_onboarding_performed
3. Call serena.initial_instructions

When changing code:
- prefer Serena symbol-based and semantic tools over raw grep or blind file-wide replace
- inspect architecture before editing
- avoid duplicate logic
- preserve existing project conventions
- summarize what was changed and why
