-- Планы отдела продаж на период. Глобальные строки (manager_id IS NULL) трактуются
-- приложением как «значение по умолчанию на каждого МОП».
--   revenue  = план оплат на МОП за месяц, ₽
--   meetings = план встреч на МОП за месяц, шт
-- Применять под каждый новый месяц (поменять период). Идемпотентно для именованных МОП;
-- для глобальных строк (NULL) запускать один раз на период.

INSERT INTO plans (period, manager_id, metric, target)
VALUES
  ('2026-06', NULL, 'revenue', 500000),
  ('2026-06', NULL, 'meetings', 20)
ON CONFLICT (period, manager_id, metric) DO UPDATE SET target = EXCLUDED.target;
