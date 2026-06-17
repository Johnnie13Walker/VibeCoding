-- Планы отдела продаж на период.
--   revenue, manager_id IS NULL  = КОМАНДНЫЙ план оплат на отдел, ₽
--   revenue, manager_id = <id>   = индивидуальный план оплат МОП, ₽
--   briefs,  manager_id IS NULL  = норматив брифов на одного МОП, шт
--   meetings,manager_id IS NULL  = норматив встреч на ТМ (legacy)
--   tm_dials60,  manager_id IS NULL = план дозвонов ≥60с на 1 ТМ/мес
--   tm_briefings,manager_id IS NULL = план состоявшихся брифований на 1 ТМ/мес
-- Идемпотентно: DELETE+INSERT по периоду (ON CONFLICT не ловит manager_id IS NULL —
-- в Postgres NULL≠NULL, иначе глобальные строки дублируются при повторном прогоне).
-- Применять под каждый новый месяц (поменять период).

BEGIN;
DELETE FROM plans WHERE period = '2026-06';
INSERT INTO plans (period, manager_id, metric, target)
VALUES
  -- Оплаты: командный 1 млн на отдел + индивидуальные 500к Деговцовой и Семенихину
  ('2026-06', NULL, 'revenue', 1000000),
  ('2026-06', 2806, 'revenue', 500000),   -- Деговцова Елизавета
  ('2026-06', 2846, 'revenue', 500000),   -- Семенихин Егор
  -- Брифы: 20 на каждого МОП
  ('2026-06', NULL, 'briefs', 20),
  -- Встречи ТМ (legacy)
  ('2026-06', NULL, 'meetings', 20),
  -- ТМ: план дозвонов ≥60с и состоявшихся брифований на 1 звонаря
  ('2026-06', NULL, 'tm_dials60', 400),
  ('2026-06', NULL, 'tm_briefings', 20);
COMMIT;
