import { describe, expect, it, vi } from 'vitest';

// Не поднимаем реальный postgres-клиент при импорте модуля.
vi.mock('@/db', () => ({ db: {} }));

import {
  buildFunnel,
  buildSalesFunnel,
  buildForecast,
  buildMeetingQuality,
  buildManagerConversions,
  buildManagerPipeline,
  buildTmActivity,
  buildMessaging,
} from '../dashboard';

describe('buildFunnel', () => {
  it('группирует открытые сделки по стадиям, считает количество и суммы', () => {
    const result = buildFunnel([
      { stage: 'C10:NEW', opportunity: 100, stuckDays: null },
      { stage: 'C10:NEW', opportunity: 200, stuckDays: 3 },
      { stage: 'C10:EXECUTING', opportunity: 50, stuckDays: null },
    ]);

    const newStage = result.find((s) => s.stage === 'C10:NEW');
    expect(newStage).toMatchObject({ label: 'Квалификация', count: 2, amount: 300 });

    const exec = result.find((s) => s.stage === 'C10:EXECUTING');
    expect(exec).toMatchObject({ label: 'Подготовка КП', count: 1, amount: 50 });
  });

  it('исключает незнакомые/закрытые стадии', () => {
    const result = buildFunnel([
      { stage: 'C10:NEW', opportunity: 100, stuckDays: null },
      { stage: 'C10:WON', opportunity: 999, stuckDays: null },
      { stage: 'C50:NEW', opportunity: 10, stuckDays: null },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].stage).toBe('C10:NEW');
  });

  it('сортирует стадии по порядку воронки', () => {
    const result = buildFunnel([
      { stage: 'C10:UC_KC7195', opportunity: 1, stuckDays: null },
      { stage: 'C10:NEW', opportunity: 1, stuckDays: null },
      { stage: 'C10:EXECUTING', opportunity: 1, stuckDays: null },
    ]);

    expect(result.map((s) => s.label)).toEqual([
      'Квалификация',
      'Подготовка КП',
      'Подготовка договора',
    ]);
  });
});

describe('buildSalesFunnel', () => {
  it('считает шаги, конверсии между ними и средний чек', () => {
    const f = buildSalesFunnel({
      dealsTotal: 40,
      dealsCold: 30,
      dealsIncoming: 10,
      firstMeetings: 20,
      presentations: 16,
      kpSent: 12,
      wonCount: 3,
      wonAmount: 600000,
    });

    expect(f.steps.map((s) => [s.key, s.count])).toEqual([
      ['deals', 40],
      ['first', 20],
      ['kp', 12],
      ['present', 16],
      ['won', 3],
    ]);
    // Первый шаг — без конверсии.
    expect(f.steps[0].convFromPrev).toBeNull();
    // first/deals=20/40, kp/first=12/20, present/kp=16/12, won/present=3/16.
    expect(f.steps[1].convFromPrev).toBe(50);
    expect(f.steps[2].convFromPrev).toBe(60);
    expect(f.steps[3].convFromPrev).toBe(133);
    expect(f.steps[4].convFromPrev).toBe(19);
    expect(f.steps[4].amount).toBe(600000);
    expect(f.avgCheck).toBe(200000);
    expect(f.dealsCold).toBe(30);
    expect(f.dealsIncoming).toBe(10);
  });

  it('конверсии не ограничены 100% (встречи опережают сделки)', () => {
    const f = buildSalesFunnel({
      dealsTotal: 9,
      dealsCold: 5,
      dealsIncoming: 4,
      firstMeetings: 14, // 14/9 = 156%
      presentations: 10,
      kpSent: 0,
      wonCount: 0,
      wonAmount: 0,
    });
    expect(f.steps[1].convFromPrev).toBe(156);
  });

  it('пустые данные не делят на ноль', () => {
    const f = buildSalesFunnel({
      dealsTotal: 0, dealsCold: 0, dealsIncoming: 0, firstMeetings: 0,
      presentations: 0, kpSent: 0, wonCount: 0, wonAmount: 0,
    });
    expect(f.steps.every((s) => s.count === 0)).toBe(true);
    expect(f.steps[1].convFromPrev).toBeNull();
    expect(f.avgCheck).toBe(0);
  });
});

describe('buildForecast', () => {
  const funnel = [
    { stage: 'C10:UC_KC7195', label: 'Подготовка договора', order: 5, count: 1, amount: 250000 },
    { stage: 'C10:FINAL_INVOICE', label: 'Догрев и переговоры', order: 4, count: 3, amount: 4000000 },
    { stage: 'C10:EXECUTING', label: 'Подготовка КП', order: 3, count: 2, amount: 2000000 },
  ];

  it('взвешивает воронку по стадиям и добавляет оплаченное', () => {
    // 250k*0.8=200k + 4M*0.25=1M + 2M*0.15=300k = 1.5M взвешенно; +0.3M оплачено = 1.8M
    const f = buildForecast(funnel, 300000, 1500000, 15, 30);
    expect(f.weighted).toBe(1_500_000);
    expect(f.forecastClose).toBe(1_800_000);
    expect(f.pct).toBe(120); // 1.8M / 1.5M
    // pacing: ожид. = 1.5M * 15/30 = 750k; факт 300k → 40%
    expect(f.paceExpected).toBe(750_000);
    expect(f.pacePct).toBe(40);
    // стадии отсортированы по взвешенному убыванию (Догрев первым)
    expect(f.byStage[0].label).toBe('Догрев и переговоры');
  });

  it('без плана выручки не делит на ноль', () => {
    const f = buildForecast(funnel, 0, 0, 10, 30);
    expect(f.pct).toBeNull();
    expect(f.paceExpected).toBe(0);
    expect(f.pacePct).toBeNull();
  });
});

describe('buildMeetingQuality', () => {
  it('средний балл, % со след.шагом, балл по типам, топ проблемных', () => {
    const q = buildMeetingQuality([
      { score: 8, hasNextStep: true, type: 'defense', note: 'сильная защита', date: '2026-06-03', manager: 'А' },
      { score: 4, hasNextStep: false, type: 'briefing', note: 'анкета вместо диалога', date: '2026-06-02', manager: 'Б' },
      { score: 6, hasNextStep: true, type: 'briefing', note: '', date: '2026-06-01', manager: 'В' },
      { score: null, hasNextStep: false, type: 'other', note: '', date: '2026-06-01', manager: 'Г' },
    ]);
    expect(q.count).toBe(4);
    expect(q.avgScore).toBe(6); // (8+4+6)/3
    expect(q.pctNextStep).toBe(50); // 2 из 4
    expect(q.defenseAvg).toBe(8);
    expect(q.briefingAvg).toBe(5); // (4+6)/2
    expect(q.problematic[0].score).toBe(4); // худшая первой
    expect(q.problematic[0].manager).toBe('Б');
  });

  it('пустой ввод не падает', () => {
    const q = buildMeetingQuality([]);
    expect(q.count).toBe(0);
    expect(q.avgScore).toBeNull();
    expect(q.pctNextStep).toBeNull();
    expect(q.problematic).toEqual([]);
  });
});

describe('buildManagerConversions', () => {
  it('считает конверсии по менеджеру и итоговую строку «Общая ОП»', () => {
    const { managers, total } = buildManagerConversions([
      { managerId: 1, name: 'А', deals: 10, first: 5, defense: 4, won: 2 },
      { managerId: 2, name: 'Б', deals: 6, first: 6, defense: 3, won: 0 },
    ]);
    expect(managers[0].dealToMeeting).toBe(50); // 5/10
    expect(managers[0].meetingToDefense).toBe(80); // 4/5
    expect(managers[0].defenseToWon).toBe(50); // 2/4
    expect(managers[0].dealToWon).toBe(20); // 2/10
    expect(managers[1].defenseToWon).toBe(0); // 0/3
    // Общая ОП: deals 16, first 11, defense 7, won 2
    expect(total.name).toBe('Общая ОП');
    expect(total.dealToMeeting).toBe(69); // 11/16
    expect(total.dealToWon).toBe(13); // 2/16
  });

  it('ноль сделок → конверсия null, без деления на ноль', () => {
    const { total } = buildManagerConversions([]);
    expect(total.deals).toBe(0);
    expect(total.dealToMeeting).toBeNull();
  });
});

describe('buildManagerPipeline', () => {
  const cells = [
    { managerId: 1, name: 'А', stage: 'C10:FINAL_INVOICE', count: 1, amount: 1000000 },
    { managerId: 1, name: 'А', stage: 'C10:EXECUTING', count: 1, amount: 500000 },
    { managerId: 2, name: 'Б', stage: 'C10:NEW', count: 1, amount: 0 },
    { managerId: 2, name: 'Б', stage: 'C10:WON', count: 1, amount: 9 }, // закрытая стадия — игнор
  ];

  it('собирает матрицу, суммы по стадии и Δ к началу месяца', () => {
    const p = buildManagerPipeline(cells, { 1: 1, 2: 3 });
    const a = p.rows.find((r) => r.managerId === 1)!;
    expect(a.total).toBe(2);
    expect(a.amount).toBe(1500000);
    expect(a.delta).toBe(1); // было 1 → стало 2
    const b = p.rows.find((r) => r.managerId === 2)!;
    expect(b.total).toBe(1); // C10:WON не считается
    expect(b.delta).toBe(-2); // было 3 → стало 1
    expect(p.rows[0].managerId).toBe(1); // сортировка по ₽ убыв.
    expect(p.stageAmount['C10:FINAL_INVOICE']).toBe(1000000);
    expect(p.grandTotal).toBe(3);
  });

  it('пустой ввод не падает', () => {
    const p = buildManagerPipeline([], {});
    expect(p.rows).toEqual([]);
    expect(p.grandTotal).toBe(0);
    expect(p.stages.length).toBe(5);
  });
});

describe('buildTmActivity', () => {
  it('суммы, на 1 звонаря, в день и конверсия во встречу', () => {
    const a = buildTmActivity(
      [
        { managerId: 1, name: 'Д', dials: 1000, calls60: 300, calls120: 200, meetingsSet: 38, talkHours: 40 },
        { managerId: 2, name: 'Г', dials: 1000, calls60: 300, calls120: 200, meetingsSet: 0, talkHours: 28 },
      ],
      20,
    );
    expect(a.zvonari).toBe(2);
    expect(a.dials).toBe(2000);
    expect(a.calls60).toBe(600);
    expect(a.dialsPerZvonar).toBe(1000);
    expect(a.dialsPerDay).toBe(100); // 2000/20
    expect(a.talkHours).toBe(68);
    // строки сортированы по наборам; конверсия = meetingsSet/dials
    expect(a.rows[0].convToMeeting).toBe(3.8); // 38/1000
    expect(a.rows[1].convToMeeting).toBe(0);
  });

  it('нет звонарей — нули, без деления на ноль', () => {
    const a = buildTmActivity([], 0);
    expect(a.zvonari).toBe(0);
    expect(a.dialsPerZvonar).toBe(0);
    expect(a.dialsPerDay).toBe(0);
  });
});

describe('buildMessaging', () => {
  it('итоги и строки без пустых, сортировка по мессенджеру', () => {
    const m = buildMessaging([
      { managerId: 1, name: 'А', messenger: 100, emails: 10 },
      { managerId: 2, name: 'Б', messenger: 0, emails: 0 },
      { managerId: 3, name: 'В', messenger: 130, emails: 5 },
    ]);
    expect(m.messengerTotal).toBe(230);
    expect(m.emailTotal).toBe(15);
    expect(m.rows.map((r) => r.name)).toEqual(['В', 'А']); // Б отфильтрован, сорт по messenger
  });
});
