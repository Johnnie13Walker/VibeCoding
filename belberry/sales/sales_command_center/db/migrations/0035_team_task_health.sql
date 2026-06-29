-- Сводка «Команда · эффективность и просрочки» на /alerts/tasks: дневной снимок
-- по каждому сотруднику ОП+РОП. КПД (наш) = доля задач, закрытых вовремя, среди
-- закрытых за 30 дней с дедлайном. Просрочки (задачи Bitrix + CRM-дела) — счётчики;
-- сами списки тянутся на detail-странице живьём из Bitrix, тут только числа.
CREATE TABLE IF NOT EXISTS team_task_health (
  report_date          DATE NOT NULL,
  manager_id           INTEGER NOT NULL,
  name                 TEXT,
  dept                 TEXT,
  is_active            BOOLEAN NOT NULL DEFAULT true,
  efficiency_pct       NUMERIC(5,2),                 -- наш КПД; NULL = нет закрытых с дедлайном
  closed_with_deadline INTEGER NOT NULL DEFAULT 0,   -- знаменатель КПД за 30 дней
  closed_ontime        INTEGER NOT NULL DEFAULT 0,   -- числитель КПД
  overdue_tasks        INTEGER NOT NULL DEFAULT 0,   -- просроченные задачи (tasks)
  overdue_activities   INTEGER NOT NULL DEFAULT 0,   -- просроченные дела (crm.activity)
  collected_at         TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (report_date, manager_id)
);

-- Владелец = app-роль (иначе psql под postgres даёт scc_app permission denied на запись).
ALTER TABLE team_task_health OWNER TO scc_app;
