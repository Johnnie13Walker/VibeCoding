-- Исход «возврата в работу» для понятного итога в интерфейсе:
-- current (вернули текущему), transferred (передали другому МОП/РОП),
-- telemarketing (перевели в воронку Телемаркетинг).
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS outcome_kind TEXT;
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS outcome_responsible_id INTEGER;
