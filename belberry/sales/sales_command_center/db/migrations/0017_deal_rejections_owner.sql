-- Денормализованный владелец сделки на момент синка отказов — чтобы блок «Отказы»
-- резолвил имя/должность/активность без зависимости от auth-таблицы users
-- (туда уволенные продажники, напр. Дудин Петр, не попадают). Заполняет
-- sync_rejections.py для cat10 (по user.get владельца). owner_active=false → тег «уволен».
ALTER TABLE deal_rejections ADD COLUMN IF NOT EXISTS owner_name text;
ALTER TABLE deal_rejections ADD COLUMN IF NOT EXISTS owner_dept text;
ALTER TABLE deal_rejections ADD COLUMN IF NOT EXISTS owner_active boolean;
