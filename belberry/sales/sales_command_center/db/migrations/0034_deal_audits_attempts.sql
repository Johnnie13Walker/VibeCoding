-- Счётчик неудачных попыток аудита. Транзиентные сбои (LLM 429/quota/rate-limit,
-- таймаут, 5xx, смерть воркера mid-run) воркер возвращает в pending с backoff, а не
-- хоронит в error сразу. attempts ограничивает число повторов, чтобы реально битый
-- аудит не крутился вечно.
ALTER TABLE deal_audits ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
