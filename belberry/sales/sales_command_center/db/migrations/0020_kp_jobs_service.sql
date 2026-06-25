-- Услуга КП-задания: seo | orm. Определяет шаблон деки (<service>-<brand>) и
-- пресет сметы. По умолчанию seo — поведение существующих заданий не меняется.
ALTER TABLE kp_jobs ADD COLUMN IF NOT EXISTS service text NOT NULL DEFAULT 'seo';
