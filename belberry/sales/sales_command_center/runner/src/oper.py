"""Метрика «Опер» — операционная вовлечённость менеджера.

Портировано 1-в-1 из Льва Петровича
(cloudbot/apps/lev_petrovich/legacy_sales_agent/sales_formatter.py
 :: _communications_scorecard, строки ~1500-1561). По этой оценке эталонная
сводка строит рейтинг менеджеров и «Тигра дня».

operational_minutes = empty_dials×1.5 (cap 90)
                     + normal_calls×(12 ТМ / 15 ОП)
                     + messenger_dialogs×10
                     + meetings×50 (только ОП)
operational_score = min(10, operational_minutes / 300 × 10)

messenger_dialogs (чаты Wazzup) считаем из Bitrix timeline по ответственному за
сделку (collect.compute_messenger_dialogs) — НЕ из webhook-архива, как у Льва
Петровича (его на нашем сервере нет), но та же роль в формуле.
"""

EMPTY_DIAL_MINUTES = 1.5
EMPTY_DIAL_MINUTES_CAP = 90.0
TM_CALL_MINUTES = 12
SM_CALL_MINUTES = 15
CHAT_DIALOG_MINUTES = 10
MEETING_MINUTES = 50
ACTIVE_CLIENT_MINUTES_TARGET = 300.0
TOP_OPERATIONAL_ENGAGEMENT_MIN = 9.0


def is_telemarketing(role: str | None) -> bool:
    return "телемарк" in (role or "").lower()


def operational_score(
    *,
    dials: int | None,
    normal_calls: int | None,
    messenger_dialogs: int | None = 0,
    meetings_count: int | None = 0,
    is_tm: bool,
) -> float:
    dials = dials or 0
    normal_calls = normal_calls or 0
    empty_dials = max(0, dials - normal_calls)
    empty_min = min(empty_dials * EMPTY_DIAL_MINUTES, EMPTY_DIAL_MINUTES_CAP)
    call_min = normal_calls * (TM_CALL_MINUTES if is_tm else SM_CALL_MINUTES)
    chat_min = (messenger_dialogs or 0) * CHAT_DIALOG_MINUTES
    meet_min = 0 if is_tm else (meetings_count or 0) * MEETING_MINUTES
    total = empty_min + call_min + chat_min + meet_min
    return round(min(10.0, total / ACTIVE_CLIENT_MINUTES_TARGET * 10.0), 1)


def oper_status(score: float) -> str:
    if score >= 6.0:
        return "НОРМ"
    if score >= 3.0:
        return "РИСК"
    return "СТОП"
