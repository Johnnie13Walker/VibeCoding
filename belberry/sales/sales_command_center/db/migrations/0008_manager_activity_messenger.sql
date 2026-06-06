-- Сохраняем чаты Wazzup (messenger_dialogs) в дневной статистике, чтобы они были
-- доступны в архивном разборе за прошлые дни. NULL = за этот день чаты не собирались
-- (дни до этой миграции); число = собрано (0 = чатов не было).
ALTER TABLE manager_activity ADD COLUMN IF NOT EXISTS messenger_dialogs integer;
