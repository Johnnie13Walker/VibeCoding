-- Дни отсутствия сотрудника (отпуск/больничный/отгул) из «Графика отсутствий» Bitrix.
-- Одна строка = один день отсутствия. Для матрицы «Опер»: помечаем «Отпуск» и
-- исключаем такие дни из среднего балла (отпуск не должен занижать оценку).
CREATE TABLE IF NOT EXISTS manager_absences (
  manager_id   integer NOT NULL,
  absence_date date NOT NULL,
  kind         text,
  PRIMARY KEY (manager_id, absence_date)
);
