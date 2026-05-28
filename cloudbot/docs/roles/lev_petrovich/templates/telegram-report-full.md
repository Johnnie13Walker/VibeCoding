# Шаблон полной сводки по продажам для Telegram

```text
📊 Сводка по продажам
Лев Петрович
Срез: {slice_time_msk}

Краткая сводка
• {summary_line_1}
• {summary_line_2}
• {summary_line_3}

📈 Воронка в работе
• Активные сделки: {deals_in_work} / <b>{pipeline_amount}</b>
• С движением за последнюю неделю: {moving_deals_last_week}
• Без движения за последнюю неделю: {stagnant_deals_last_week}
• Этап договора: {contract_stage_deals} / <b>{contract_stage_amount}</b>
• Под риском: {risk_deals} / <b>{risk_amount}</b>
  - Без следующего шага: {without_next_step_deals} / <b>{without_next_step_amount}</b>
  - Без коммуникации > 14 дн.: {stale_deals} / <b>{stale_amount}</b>
  - С просроченными задачами: {overdue_deal_task_deals} / <b>{overdue_deal_task_amount}</b>

📞 Коммуникации за предыдущий рабочий день
Статус: 🔥 НОРМ | ⚠️ РИСК | ❌ СТОП
<pre>
{communications_table}
</pre>

Итого по отделу:
<pre>
{communications_totals}
</pre>

{communications_summary_line}

🚨 Сделки без коммуникации > 14 дн.
Всего: {stale_deals} / <b>{stale_amount}</b>
• {stale_deal_1}
• {stale_deal_2}
• {stale_deal_3}
или:
Нет сделок без коммуникации более 14 дней

⚠️ Сделки без следующего шага
Всего: {without_next_step_deals} / <b>{without_next_step_amount}</b>
• {without_next_step_deal_1}
• {without_next_step_deal_2}
• {without_next_step_deal_3}
или:
Нет сделок без следующего шага

🗂 Просрочки по менеджерам
• {manager_name_1} — {overdue_count_1} просрочки, макс: {max_overdue_1}
примеры: {overdue_example_1}; {overdue_example_2}
• {manager_name_2} — {overdue_count_2} просрочки, макс: {max_overdue_2}
примеры: {overdue_example_3}

🎯 Фокус РОПа

Где потерян контроль:
• {focus_control_loss_1}
• {focus_control_loss_2}
• {focus_control_loss_3}

💸 Где взять деньги сегодня:
• {focus_money_today_1}
• {focus_money_today_2}
• {focus_money_today_3}

☎️ Где РОПу самому связаться с клиентом:
• {focus_escalation_1}
• {focus_escalation_2}

🕳 Упущенные возможности:
• {focus_opportunity_1}
• {focus_opportunity_2}
• {focus_opportunity_3}

Кого дожать сегодня:
• {focus_push_manager_1}
• {focus_push_manager_2}
• {focus_push_manager_3}

Что РОП обязан сделать сегодня:
• {focus_action_1}
• {focus_action_2}
• {focus_action_3}

🔥 Молодцы за вчера
• {focus_yesterday_star_1}
• {focus_yesterday_star_2}
• {focus_yesterday_star_3}
```
