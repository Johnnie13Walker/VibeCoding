"""Управленческий анализ финансовых данных."""

from __future__ import annotations

from typing import Any

from apps.finansist.schemas.finance import FinanceRequest, FinanceSourceSnapshot


def analyze_finance_request(request: FinanceRequest, snapshot: FinanceSourceSnapshot) -> dict[str, Any]:
    metrics = dict(request.metrics or {})
    facts: list[str] = []
    conclusions: list[str] = []
    hypotheses: list[str] = list(request.facts or ())
    actions: list[str] = []
    missing: list[str] = list(snapshot.missing_requirements)

    if snapshot.sources:
        accessible = [source for source in snapshot.sources if source.access_status == "ready"]
        google_docs = [source for source in snapshot.sources if source.source_type == "google_doc"]
        google_sheets = [source for source in snapshot.sources if source.source_type == "google_sheet"]
        facts.append(
            f"Подключено источников: {len(snapshot.sources)}, из них ready: {len(accessible)}."
        )
        if google_docs:
            facts.append(
                "Google Docs "
                + ("доступ подтвержден." if snapshot.google_docs_access_ready else "обнаружены, но credential path не подтвержден.")
            )
        if google_sheets:
            facts.append(
                "Google Sheets "
                + ("доступ подтвержден." if snapshot.google_sheets_access_ready else "обнаружены, но credential path не подтвержден.")
            )

    _append_margin_findings(metrics, facts, conclusions, hypotheses)
    _append_payroll_findings(metrics, facts, conclusions, hypotheses)
    _append_cashflow_findings(metrics, facts, conclusions, hypotheses)
    _append_fact_plan_findings(metrics, facts, conclusions)
    _append_client_findings(metrics, facts, conclusions, hypotheses)
    _append_receivables_findings(metrics, facts, conclusions, hypotheses)

    missing.extend(_required_metrics_for_focus(request.focus, metrics))

    if not conclusions:
        conclusions.append("Недостаточно подтвержденных цифр для жесткого управленческого вывода.")

    if not actions:
        actions.extend(_build_actions(metrics, conclusions))

    summary = conclusions[0]
    text = "\n".join(
        [
            "1. Суть",
            summary,
            "",
            "2. Что вижу по цифрам",
            _format_items("Факты", facts),
            "",
            "3. Риски",
            _format_items("Выводы", conclusions),
            "",
            "4. Причины или гипотезы причин",
            _format_items("Гипотезы", hypotheses or ("Гипотез пока недостаточно: не хватает детализации по статьям и периодам.",)),
            "",
            "5. Что делать",
            _format_items("Действия", actions),
            "",
            "6. Какие данные еще нужны",
            _format_items("Нехватка данных", tuple(dict.fromkeys(item for item in missing if item))),
        ]
    ).strip()

    return {
        "summary": summary,
        "text": text,
        "facts": facts,
        "conclusions": conclusions,
        "hypotheses": hypotheses,
        "actions": actions,
        "missing_data": tuple(dict.fromkeys(item for item in missing if item)),
    }


def _append_margin_findings(metrics: dict[str, Any], facts: list[str], conclusions: list[str], hypotheses: list[str]) -> None:
    revenue_current = _to_float(metrics.get("revenue_current"))
    revenue_previous = _to_float(metrics.get("revenue_previous"))
    gross_profit_current = _to_float(metrics.get("gross_profit_current"))
    gross_profit_previous = _to_float(metrics.get("gross_profit_previous"))
    if revenue_current is None or gross_profit_current is None:
        return
    gross_margin_current = _ratio(gross_profit_current, revenue_current)
    if gross_margin_current is not None:
        facts.append(f"Текущая валовая маржа: {gross_margin_current:.1%}.")
    if revenue_previous is None or gross_profit_previous is None:
        return
    gross_margin_previous = _ratio(gross_profit_previous, revenue_previous)
    if gross_margin_previous is None:
        return
    delta = gross_margin_current - gross_margin_previous
    facts.append(f"Изменение валовой маржи к прошлому периоду: {delta:+.1%}.")
    if delta <= -0.05:
        conclusions.append(f"Маржа просела на {delta:+.1%}. Экономика продаж ухудшается.")
        hypotheses.append("Провал может идти из скидок, перерасхода production-себестоимости или роста ФОТ без пересмотра цен.")


def _append_payroll_findings(metrics: dict[str, Any], facts: list[str], conclusions: list[str], hypotheses: list[str]) -> None:
    payroll_current = _to_float(metrics.get("payroll_current"))
    revenue_current = _to_float(metrics.get("revenue_current"))
    payroll_previous = _to_float(metrics.get("payroll_previous"))
    if payroll_current is None or revenue_current in (None, 0):
        return
    payroll_share = payroll_current / revenue_current
    facts.append(f"Нагрузка ФОТ на выручку: {payroll_share:.1%}.")
    if payroll_share >= 0.35:
        conclusions.append(f"ФОТ перегрет: {payroll_share:.1%} от выручки.")
    if payroll_previous is not None and payroll_current > payroll_previous * 1.15:
        hypotheses.append("ФОТ вырос быстрее бизнеса. Нужно проверить рост headcount, роль low-utilization сотрудников и переаллокацию на клиентов.")


def _append_cashflow_findings(metrics: dict[str, Any], facts: list[str], conclusions: list[str], hypotheses: list[str]) -> None:
    cash_balance = _to_float(metrics.get("cash_balance_current"))
    cash_in_4w = _to_float(metrics.get("cash_in_4w"))
    cash_out_4w = _to_float(metrics.get("cash_out_4w"))
    if cash_balance is None or cash_in_4w is None or cash_out_4w is None:
        return
    projected_gap = cash_balance + cash_in_4w - cash_out_4w
    facts.append(f"Прогноз кассы на 4 недели: {projected_gap:,.0f}.".replace(",", " "))
    if projected_gap < 0:
        conclusions.append(f"Риск кассового разрыва в горизонте 4 недель: {projected_gap:,.0f}.".replace(",", " "))
        hypotheses.append("Нужно проверить график поступлений по дебиторке и обязательные платежи без права сдвига.")


def _append_fact_plan_findings(metrics: dict[str, Any], facts: list[str], conclusions: list[str]) -> None:
    actual_revenue = _to_float(metrics.get("actual_revenue_current"))
    planned_revenue = _to_float(metrics.get("planned_revenue_current"))
    actual_expenses = _to_float(metrics.get("actual_expenses_current"))
    planned_expenses = _to_float(metrics.get("planned_expenses_current"))
    if actual_revenue is not None and planned_revenue not in (None, 0):
        revenue_delta = (actual_revenue - planned_revenue) / planned_revenue
        facts.append(f"Отклонение выручки к плану: {revenue_delta:+.1%}.")
        if revenue_delta <= -0.1:
            conclusions.append(f"План по выручке провален на {revenue_delta:+.1%}.")
    if actual_expenses is not None and planned_expenses not in (None, 0):
        expense_delta = (actual_expenses - planned_expenses) / planned_expenses
        facts.append(f"Отклонение расходов к плану: {expense_delta:+.1%}.")
        if expense_delta >= 0.1:
            conclusions.append(f"Расходы выше плана на {expense_delta:+.1%}.")


def _append_client_findings(
    metrics: dict[str, Any],
    facts: list[str],
    conclusions: list[str],
    hypotheses: list[str],
) -> None:
    top_client_share = _to_float(metrics.get("top_client_share"))
    if top_client_share is not None:
        facts.append(f"Доля топ-клиента в выручке: {top_client_share:.1%}.")
        if top_client_share >= 0.3:
            conclusions.append(f"Слишком высокая концентрация выручки на одном клиенте: {top_client_share:.1%}.")
    client_items = metrics.get("client_profitability") or ()
    worst_clients: list[str] = []
    for item in client_items:
        if not isinstance(item, dict):
            continue
        margin = _to_float(item.get("profit_margin"))
        name = str(item.get("name") or "Клиент")
        if margin is not None and margin <= 0:
            worst_clients.append(f"{name} ({margin:.1%})")
    if worst_clients:
        conclusions.append("Есть убыточные или нулевые клиенты: " + ", ".join(worst_clients[:3]) + ".")
        hypotheses.append("Проверьте scope creep, перерасход часов и заниженный прайс по этим клиентам.")


def _append_receivables_findings(
    metrics: dict[str, Any],
    facts: list[str],
    conclusions: list[str],
    hypotheses: list[str],
) -> None:
    overdue_receivables = _to_float(metrics.get("receivables_overdue"))
    total_receivables = _to_float(metrics.get("receivables_total"))
    if overdue_receivables is not None:
        facts.append(f"Просроченная дебиторка: {overdue_receivables:,.0f}.".replace(",", " "))
    if overdue_receivables is not None and total_receivables not in (None, 0):
        overdue_share = overdue_receivables / total_receivables
        facts.append(f"Доля просроченной дебиторки: {overdue_share:.1%}.")
        if overdue_share >= 0.25:
            conclusions.append(f"Дебиторка токсична: {overdue_share:.1%} портфеля уже просрочено.")
            hypotheses.append("Нужен разбор по клиентам, срокам просрочки и ответственным за выбивание оплат.")


def _required_metrics_for_focus(focus: str, metrics: dict[str, Any]) -> list[str]:
    required_by_focus = {
        "finance_summary": ("revenue_current", "gross_profit_current", "cash_balance_current"),
        "pnl_analysis": ("revenue_current", "gross_profit_current", "operating_profit_current"),
        "cashflow_analysis": ("cash_balance_current", "cash_in_4w", "cash_out_4w"),
        "expense_structure_analysis": ("actual_expenses_current", "planned_expenses_current", "payroll_current"),
        "client_profitability_analysis": ("client_profitability", "revenue_current"),
        "receivables_analysis": ("receivables_total", "receivables_overdue"),
        "payables_analysis": ("payables_total", "cash_out_4w"),
        "finance_anomaly_scan": ("revenue_current", "actual_expenses_current", "gross_profit_current"),
    }
    missing: list[str] = []
    for key in required_by_focus.get(focus, ()):
        value = metrics.get(key)
        if value is None or value == () or value == [] or value == {}:
            missing.append(f"Нет метрики `{key}` для сценария `{focus}`.")
    return missing


def _build_actions(metrics: dict[str, Any], conclusions: list[str]) -> list[str]:
    actions: list[str] = []
    if any("кассового разрыва" in item for item in conclusions):
        actions.append("Собрать недельный платежный календарь и вручную подтвердить все крупные списания без права переноса.")
        actions.append("Поднять приоритет выбивания просроченной дебиторки и привязать ее к конкретным ответственным.")
    if any("ФОТ перегрет" in item for item in conclusions):
        actions.append("Разложить ФОТ по клиентам и направлениям, чтобы найти non-billable нагрузку и слабые роли.")
    if any("Маржа просела" in item for item in conclusions):
        actions.append("Проверить 5 крупнейших клиентов на скидки, перерасход часов и убыточные scope changes.")
    if any("Расходы выше плана" in item for item in conclusions):
        actions.append("Отдельно разобрать статьи с ростом расходов выше 10% без роста выручки.")
    if not actions:
        actions.append("Сначала дособрать недостающие цифры по выручке, расходам, кассе и дебиторке; без этого выводы будут неполными.")
    return actions


def _format_items(title: str, items: tuple[str, ...] | list[str]) -> str:
    prepared = [str(item).strip() for item in items if str(item).strip()]
    if not prepared:
        return f"{title}: данных пока недостаточно."
    return "\n".join([f"{title}:"] + [f"- {item}" for item in prepared])


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
