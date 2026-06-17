"""Заполнение пользовательского Sheet «Дашборд ОП» (sheet_id 1mAN...HBuGdM).

Скрипт читает данные из Bitrix и пишет в табы «Май 26» + «Новый даш».
Правила (от пользователя 2026-05-21):
- Лиды = все сделки CATEGORY=10 created в периоде (минус спам/дубль если будут размечены)
- Сделки в работе = лиды AND not in LOSE/ОТЛОЖЕНО
- Договоров начато = текущее в C10:UC_KC7195 + WON в периоде
- Везде использовать ФАМИЛИЮ менеджера, не имя

Запуск (после bitrix-sync-state.sh):
  python3 scripts/fill_dashboard_op.py
"""
# См. /tmp/fill_dashboard_op_full.py — версия запущенная 2026-05-21
# TODO: переписать в модуль sales_kpi_dashboard/external_dashboard.py + CLI команду в Phase 6
