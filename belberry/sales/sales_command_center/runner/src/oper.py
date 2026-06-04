"""Метрика «Опер» — операционная вовлечённость менеджера.

Модель «реальных рабочих минут»: каждое действие переводим в живое время, на
которое оно реально занимает менеджера, суммируем и нормируем к дню (≈5 рабочих
часов «в руках»). Так ОП и ТМ сравниваются честно — встреча весит как встреча,
а пустой набор как пустой набор, без перекоса в сторону объёма обзвона.

operational_minutes = short_dials×0.25 (cap 90)   # набор/короткий обрыв = 15 сек
                    + calls_60s×5                  # разговор 60с+ = 5 мин
                    + messenger_dialogs×10         # чат Wazzup = 10 мин
                    + emails×5                     # письмо = 5 мин
                    + meetings×60                  # встреча = 60 мин
operational_score   = min(10, operational_minutes / 300 × 10)

«Дозвоном» в формуле считаем именно звонок 60с+ (calls_60s_plus) — короткие
соединения (<60с) идут только как набор. messenger_dialogs (чаты Wazzup) —
из Bitrix timeline по ответственному за сделку (collect.compute_messenger_dialogs).

Раньше формула была портом 1-в-1 из Льва Петровича (sales_formatter.py
:: _communications_scorecard) с весами дозвон×12/15 и встреча×50; с переходом на
модель реальных минут она специфична для Global Sales Dashboard и роль (ТМ/ОП)
на сам балл больше не влияет.
"""

DIAL_MINUTES = 0.25
DIAL_MINUTES_CAP = 90.0
CALL_60S_MINUTES = 5
CHAT_DIALOG_MINUTES = 10
EMAIL_MINUTES = 5
MEETING_MINUTES = 60
DAY_TARGET_MINUTES = 300.0
TOP_OPERATIONAL_ENGAGEMENT_MIN = 9.0


def is_telemarketing(role: str | None) -> bool:
    return "телемарк" in (role or "").lower()


def operational_minutes(
    *,
    dials: int | None,
    calls_60s: int | None,
    messenger_dialogs: int | None = 0,
    meetings_count: int | None = 0,
    emails: int | None = 0,
) -> float:
    """Сумма «живых» рабочих минут за день по действиям менеджера."""
    dials = dials or 0
    calls_60s = calls_60s or 0
    short_dials = max(0, dials - calls_60s)
    dial_min = min(short_dials * DIAL_MINUTES, DIAL_MINUTES_CAP)
    call_min = calls_60s * CALL_60S_MINUTES
    chat_min = (messenger_dialogs or 0) * CHAT_DIALOG_MINUTES
    email_min = (emails or 0) * EMAIL_MINUTES
    meet_min = (meetings_count or 0) * MEETING_MINUTES
    return dial_min + call_min + chat_min + email_min + meet_min


def operational_score(
    *,
    dials: int | None,
    calls_60s: int | None,
    messenger_dialogs: int | None = 0,
    meetings_count: int | None = 0,
    emails: int | None = 0,
) -> float:
    total = operational_minutes(
        dials=dials,
        calls_60s=calls_60s,
        messenger_dialogs=messenger_dialogs,
        meetings_count=meetings_count,
        emails=emails,
    )
    return round(min(10.0, total / DAY_TARGET_MINUTES * 10.0), 1)


def oper_status(score: float) -> str:
    if score >= 6.0:
        return "НОРМ"
    if score >= 3.0:
        return "РИСК"
    return "СТОП"
