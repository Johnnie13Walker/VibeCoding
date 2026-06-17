#!/usr/bin/env python3
"""Smoke test Cloudbot: тесты бота и ключевых контуров без News."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_step(title: str, cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    print(f"[STEP] {title}")
    completed = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout.strip())
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"Smoke step failed: {title}")


def main() -> None:
    run_step("bot npm test", ["npm", "test"], cwd=BOT_DIR)

    smoke_google_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    smoke_finance_sheet = os.environ.get("FINANSIST_SMOKE_SHEET_URL", "").strip()
    if smoke_google_key and smoke_finance_sheet:
        run_step(
            "finansist Google Sheets smoke",
            [
                "node",
                "checks/finansist_google_smoke.mjs",
                "--sheet-url",
                smoke_finance_sheet,
            ],
            env={
                "GOOGLE_SERVICE_ACCOUNT_JSON": smoke_google_key,
            },
        )
    else:
        print("[STEP] finansist Google Sheets smoke пропущен: не заданы GOOGLE_SERVICE_ACCOUNT_JSON и FINANSIST_SMOKE_SHEET_URL")

    print("[STEP] orchestrator получает сообщение")
    from cloudbot.orchestrator.orchestrator import handle_incoming_message

    result = handle_incoming_message({"text": "/today", "command": "/today", "chat_id": "1", "user_id": "1"})
    workflow = result.get("workflow")
    if workflow != "day_briefing":
        raise SystemExit(f"Ожидался workflow day_briefing, получен {workflow}")
    print("orchestrator OK:", result.get("text"))

    print("[STEP] orchestrator получает финансовый запрос")
    finance_result = handle_incoming_message({
        "text": "/finance",
        "command": "/finance",
        "chat_id": "1",
        "user_id": "1",
        "metrics": {
            "revenue_current": 1000000,
            "revenue_previous": 1000000,
            "gross_profit_current": 250000,
            "gross_profit_previous": 350000,
            "payroll_current": 420000,
            "payroll_previous": 330000,
            "cash_balance_current": 150000,
            "cash_in_4w": 350000,
            "cash_out_4w": 700000,
        },
        "sources": [
            "https://docs.google.com/document/d/doc-id/edit",
            "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
        ],
    })
    if finance_result.get("workflow") != "finance_summary":
        raise SystemExit(f"Команда /finance не попала в finance_summary workflow: {finance_result.get('workflow')}")
    finance_text = str(finance_result.get("text") or "")
    if "Маржа просела" not in finance_text:
        raise SystemExit("Команда /finance не вернула управленческий финансовый вывод")
    if "Google Docs" not in finance_text or "Google Sheets" not in finance_text:
        raise SystemExit("Команда /finance не показала статус Google Docs/Sheets")
    print("orchestrator /finance OK:", finance_text.splitlines()[0])

    print("[STEP] telegram handler формирует ответ")
    from cloudbot.bot.telegram.telegram_handler import handle_update

    update_result = handle_update({
        "message": {
            "text": "/tasks",
            "chat": {"id": 700700},
            "from": {"id": 100500},
        }
    })
    response_workflow = update_result["result"].get("workflow")
    if response_workflow != "tasks_summary":
        raise SystemExit(f"Telegram->orchestrator маршрут сломан: {response_workflow}")
    if "Сводка задач подготовлена." in update_result["reply_text"]:
        raise SystemExit("Команда /tasks все еще идет в legacy summary вместо контура Ларисы")
    print("telegram handler OK:", update_result["reply_text"])

    print("[STEP] News и битые команды удалены, /search активен для Ларисы")
    from cloudbot.bot.telegram.commands import extract_command
    from cloudbot.orchestrator.router import COMMAND_ROUTES

    for command in ("/news", "/add-meeting", "/create-event"):
        if extract_command(command) is not None:
            raise SystemExit(f"Команда {command} все еще торчит в Telegram alias layer")
        if command in COMMAND_ROUTES:
            raise SystemExit(f"Команда {command} все еще торчит в router")
    if extract_command("/search") != "/search":
        raise SystemExit("Команда /search не активна в Telegram alias layer")
    if COMMAND_ROUTES.get("/search") != "larisa_search":
        raise SystemExit("Команда /search не ведет в larisa_search")
    print("command surface OK")

    print("[STEP] команда /health")
    old_health_mode = os.environ.get("SYSTEM_HEALTH_MODE")
    os.environ["SYSTEM_HEALTH_MODE"] = "mock"
    try:
        health_result = handle_update({
            "message": {
                "text": "/health",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
    finally:
        if old_health_mode is None:
            os.environ.pop("SYSTEM_HEALTH_MODE", None)
        else:
            os.environ["SYSTEM_HEALTH_MODE"] = old_health_mode

    if health_result["result"].get("workflow") != "system_health":
        raise SystemExit("Команда /health не попала в system_health workflow")
    if "<b>🟢 Статус системы</b>" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не вернула итоговый статус")
    if "<b>Интеграции</b>" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала блок API и интеграций")
    if "<b>Пользовательские возможности</b>" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала блок пользовательских возможностей")
    if "Telegram — 🟢 Работает" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала статус Telegram")
    if "Bitrix portal — 🟢 Работает" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала статус Bitrix portal")
    if "web_search skill — 🟢 Работает" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала отдельный статус web_search skill")
    if "Web search для Ларисы — 🟢 Работает" not in health_result["reply_text"]:
        raise SystemExit("Команда /health не показала отдельный capability-статус web search для Ларисы")
    print("telegram /health OK")

    print("[STEP] команды Sales Copilot и Bitrix check")
    old_sales_mock = os.environ.get("SALES_COPILOT_MOCK")
    old_bitrix_mock = os.environ.get("BITRIX_CHECK_MOCK")
    os.environ["SALES_COPILOT_MOCK"] = "1"
    os.environ["BITRIX_CHECK_MOCK"] = "1"
    try:
        sales_result = handle_update({
            "message": {
                "text": "/sales",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
        pipeline_result = handle_update({
            "message": {
                "text": "/pipeline",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
        risks_result = handle_update({
            "message": {
                "text": "/risks",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
        focus_result = handle_update({
            "message": {
                "text": "/focus-sales",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
        bitrix_result = handle_update({
            "message": {
                "text": "/bitrixcheck",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
    finally:
        if old_sales_mock is None:
            os.environ.pop("SALES_COPILOT_MOCK", None)
        else:
            os.environ["SALES_COPILOT_MOCK"] = old_sales_mock
        if old_bitrix_mock is None:
            os.environ.pop("BITRIX_CHECK_MOCK", None)
        else:
            os.environ["BITRIX_CHECK_MOCK"] = old_bitrix_mock

    if sales_result["result"].get("workflow") != "sales_brief":
        raise SystemExit("Команда /sales не попала в sales_brief workflow")
    if sales_result["result"].get("parse_mode") != "HTML":
        raise SystemExit("Команда /sales не выставила HTML parse mode")
    if "📊 Sales Copilot" not in sales_result["reply_text"]:
        raise SystemExit("Команда /sales не вернула sales brief")
    sales_chunks = sales_result["result"].get("message_chunks") or []
    if len(sales_chunks) != 3:
        raise SystemExit("Команда /sales должна вернуть отдельные сообщения для Sales Copilot, рисков и Фокуса РОПа")
    if "🚨 Риски по продажам" not in str(sales_chunks[1]):
        raise SystemExit("Команда /sales не вернула отдельный risks-отчёт вторым сообщением")
    if "🎯 Фокус РОПа" not in str(sales_chunks[2]):
        raise SystemExit("Команда /sales не вернула отдельный Фокус РОПа третьим сообщением")

    if pipeline_result["result"].get("workflow") != "sales_brief":
        raise SystemExit("Команда /pipeline не попала в sales_brief workflow")
    if "📊 Pipeline" not in pipeline_result["reply_text"]:
        raise SystemExit("Команда /pipeline не вернула pipeline report")

    if risks_result["result"].get("workflow") != "sales_brief":
        raise SystemExit("Команда /risks не попала в sales_brief workflow")
    if "🚨 Риски по продажам" not in risks_result["reply_text"]:
        raise SystemExit("Команда /risks не вернула risks report")

    if focus_result["result"].get("workflow") != "sales_brief":
        raise SystemExit("Команда /focus-sales не попала в sales_brief workflow")
    if "🎯 Фокус РОПа" not in focus_result["reply_text"]:
        raise SystemExit("Команда /focus-sales не вернула focus report")
    if "🧊 Сделки без следующего шага" in focus_result["reply_text"]:
        raise SystemExit("Команда /focus-sales не должна дублировать отдельный список сделок без следующего шага")

    if bitrix_result["result"].get("workflow") != "bitrix_check":
        raise SystemExit("Команда /bitrixcheck не попала в bitrix_check workflow")
    if "Bitrix connection:" not in bitrix_result["reply_text"]:
        raise SystemExit("Команда /bitrixcheck не вернула текст live-проверки Bitrix")
    print("telegram /sales + /bitrixcheck OK")

    print("[STEP] self-healing чинит кеш и лог")
    from cloudbot.devops.self_healing import run_self_healing

    repair_cache_file = Path(tempfile.gettempdir()) / "cloudbot_self_healing_cache.json"
    repair_log_file = Path(tempfile.gettempdir()) / "cloudbot_self_healing_runtime.log"
    repair_self_log_file = Path(tempfile.gettempdir()) / "cloudbot_self_healing.log"
    repair_rotated_log = Path(f"{repair_log_file}.1")
    repair_cache_file.write_text("{broken json", encoding="utf-8")
    repair_log_file.write_text("x" * 2048, encoding="utf-8")
    if repair_rotated_log.exists():
        repair_rotated_log.unlink()
    if repair_self_log_file.exists():
        repair_self_log_file.unlink()

    old_self_healing_mode = os.environ.get("SELF_HEALING_MODE")
    old_repair_cache = os.environ.get("SELF_HEALING_CACHE_FILE")
    old_repair_log = os.environ.get("SELF_HEALING_TARGET_LOG_FILE")
    old_self_healing_log = os.environ.get("SELF_HEALING_LOG_FILE")
    old_rotate_limit = os.environ.get("SELF_HEALING_LOG_ROTATE_BYTES")
    os.environ["SELF_HEALING_MODE"] = "mock"
    os.environ["SELF_HEALING_CACHE_FILE"] = str(repair_cache_file)
    os.environ["SELF_HEALING_TARGET_LOG_FILE"] = str(repair_log_file)
    os.environ["SELF_HEALING_LOG_FILE"] = str(repair_self_log_file)
    os.environ["SELF_HEALING_LOG_ROTATE_BYTES"] = "1024"
    try:
        healing_result = run_self_healing(os.environ)
        repair_result = handle_update({
            "message": {
                "text": "/repair",
                "chat": {"id": 700700},
                "from": {"id": 100500},
            }
        })
    finally:
        if old_self_healing_mode is None:
            os.environ.pop("SELF_HEALING_MODE", None)
        else:
            os.environ["SELF_HEALING_MODE"] = old_self_healing_mode
        if old_repair_cache is None:
            os.environ.pop("SELF_HEALING_CACHE_FILE", None)
        else:
            os.environ["SELF_HEALING_CACHE_FILE"] = old_repair_cache
        if old_repair_log is None:
            os.environ.pop("SELF_HEALING_TARGET_LOG_FILE", None)
        else:
            os.environ["SELF_HEALING_TARGET_LOG_FILE"] = old_repair_log
        if old_self_healing_log is None:
            os.environ.pop("SELF_HEALING_LOG_FILE", None)
        else:
            os.environ["SELF_HEALING_LOG_FILE"] = old_self_healing_log
        if old_rotate_limit is None:
            os.environ.pop("SELF_HEALING_LOG_ROTATE_BYTES", None)
        else:
            os.environ["SELF_HEALING_LOG_ROTATE_BYTES"] = old_rotate_limit
        for temp_path in [repair_cache_file, repair_log_file, repair_rotated_log, repair_self_log_file]:
            if temp_path.exists():
                temp_path.unlink()

    if healing_result["checks"]["cache"].get("status") != "recreated":
        raise SystemExit("Self-healing не пересоздал поврежденный кеш")
    if healing_result["checks"]["logs"].get("status") != "rotated":
        raise SystemExit("Self-healing не выполнил ротацию большого лога")
    if "SELF HEALING REPORT" not in healing_result.get("text", ""):
        raise SystemExit("Self-healing не сформировал отчет")
    if repair_result["result"].get("workflow") != "self_healing":
        raise SystemExit("Команда /repair не попала в self_healing workflow")
    if "SELF HEALING REPORT" not in repair_result["reply_text"]:
        raise SystemExit("Команда /repair не вернула self-healing отчет")
    print("self-healing OK")

    print("[STEP] scheduler содержит self_healing job")
    run_step(
        "bot scheduler self_healing job",
        [
            "node",
            "--input-type=module",
            "-e",
            "import { createBotModules } from './src/index.js'; const modules = createBotModules(process.env); const names = modules.schedulerJobs.map((job) => job.name); if (!names.includes('self_healing')) { throw new Error(`scheduler jobs missing self_healing: ${names.join(',')}`); } console.log(names.join(','));",
        ],
        cwd=BOT_DIR,
    )

    run_step(
        "telegram dry-run jobs",
        ["node", "./scripts/run_jobs_once.js"],
        cwd=BOT_DIR,
        env={
            "TELEGRAM_OWNER_ID": "100500",
            "TELEGRAM_CHAT_ID": "700700",
            "TELEGRAM_DRY_RUN": "1",
            "USE_FIXTURE_TASKS": "1",
            "USE_FIXTURE_USERS": "1",
        },
    )

    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
