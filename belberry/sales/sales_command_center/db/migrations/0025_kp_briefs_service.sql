-- Услуга брифа/КП в истории: раннер несёт kp_briefs.service (зеркало live.py
-- SERVICE_MAP/KP_SERVICE_MAP). Нужна, чтобы услуга показывалась не только в live
-- «Сегодня», но и при переключении на прошлую дату (getDayBreakdown). NULL/'' — услуга
-- в сделке не выбрана. Заполняется дневным/flow-раннером; история — бэкафиллом.
ALTER TABLE kp_briefs ADD COLUMN IF NOT EXISTS service text;
