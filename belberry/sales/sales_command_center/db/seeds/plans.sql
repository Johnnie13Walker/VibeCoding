-- Планы отдела продаж на период.
--   revenue, manager_id IS NULL  = КОМАНДНЫЙ план оплат на отдел, ₽
--   revenue, manager_id = <id>   = индивидуальный план оплат МОП, ₽
--   briefs,  manager_id IS NULL  = норматив брифов на одного МОП, шт
--   meetings,manager_id IS NULL  = норматив встреч на ТМ (на Дашборде ТМ)
-- Применять под каждый новый месяц (поменять период). Идемпотентно (upsert).

INSERT INTO plans (period, manager_id, metric, target)
VALUES
  -- Оплаты: командный 1 млн на отдел + индивидуальные 500к Деговцовой и Семенихину
  ('2026-06', NULL, 'revenue', 1000000),
  ('2026-06', 2806, 'revenue', 500000),   -- Деговцова Елизавета
  ('2026-06', 2846, 'revenue', 500000),   -- Семенихин Егор
  -- Брифы: 20 на каждого МОП
  ('2026-06', NULL, 'briefs', 20),
  -- Встречи ТМ (для Дашборда ТМ)
  ('2026-06', NULL, 'meetings', 20)
ON CONFLICT (period, manager_id, metric) DO UPDATE SET target = EXCLUDED.target;
