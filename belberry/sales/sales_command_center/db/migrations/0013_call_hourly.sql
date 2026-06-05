-- Почасовая агрегация звонков (для heatmap «когда берут трубку»): на день,
-- менеджера и час МСК — наборы/ответы/дозвоны ≥60с. Heatmap (час × день недели)
-- считается SQL-запросом по этой таблице. Час из CALL_START_DATE (offset +03:00).
CREATE TABLE IF NOT EXISTS call_hourly (
  report_date date NOT NULL,
  manager_id integer NOT NULL,
  hour smallint NOT NULL,
  dials integer DEFAULT 0,
  answered integer DEFAULT 0,
  calls60 integer DEFAULT 0,
  PRIMARY KEY (report_date, manager_id, hour)
);
CREATE INDEX IF NOT EXISTS call_hourly_manager_date_idx ON call_hourly (manager_id, report_date);
