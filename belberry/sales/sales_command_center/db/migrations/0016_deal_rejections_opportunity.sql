-- Сумма проигранной сделки (OPPORTUNITY на момент отказа) — для блока «Отказы»
-- на Дашборде ОП: метрика «Потеряно ₽» и средняя потеря. Заполняется
-- sync_rejections.py при апсерте закрытых сделок (cat10 C10:LOSE и cat50).
ALTER TABLE deal_rejections ADD COLUMN IF NOT EXISTS opportunity numeric(14, 2);
