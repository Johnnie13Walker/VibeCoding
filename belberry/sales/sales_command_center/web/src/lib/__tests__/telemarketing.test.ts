import { describe, expect, it } from 'vitest';
import {
  STAGE_META_50,
  isTelemarketing,
  buildTmKpis,
  buildTmManagerTable,
  buildTmMicroFunnel,
  buildTmFunnel50,
  buildTmMonthly,
  buildTmMeetingsResult,
  buildTmPlanFact,
  buildTmOutreach,
  buildTmRejections,
  buildTmHeatmap,
  buildTmMeetingQuality,
  buildTmAlerts,
  type TmMember,
} from '@/lib/telemarketing-shared';

// Реальные числа из отчёта ТМ (май 2026) — фиксируем расчёт на достоверных данных.
const isaeva: TmMember = {
  managerId: 2772, name: 'Дарья Исаева', dept: 'Телемаркетолог',
  dials: 1336, answered: 928, calls60: 370, calls120: 0, talkSeconds: 904 * 60,
  meetingsSet: 14, meetingsHeldByCreator: 12, rejectionsPeriod: 77, dealsCold: 0, messenger: 0, emails: 0,
};
const vostretsov: TmMember = {
  managerId: 2832, name: 'Аркадий Вострецов', dept: 'Телемаркетолог',
  dials: 1220, answered: 692, calls60: 219, calls120: 0, talkSeconds: 637 * 60,
  meetingsSet: 14, meetingsHeldByCreator: 11, rejectionsPeriod: 236, dealsCold: 0, messenger: 0, emails: 0,
};

describe('isTelemarketing', () => {
  it('ловит должность телемаркетолога без учёта регистра', () => {
    expect(isTelemarketing('Телемаркетолог')).toBe(true);
    expect(isTelemarketing('старший телемаркетинг')).toBe(true);
  });
  it('исключает прочие должности и пустые', () => {
    expect(isTelemarketing('Менеджер по продажам')).toBe(false);
    expect(isTelemarketing('')).toBe(false);
    expect(isTelemarketing(null)).toBe(false);
    expect(isTelemarketing(undefined)).toBe(false);
  });
});

describe('STAGE_META_50', () => {
  it('содержит ключевые стадии воронки [50] с правильным типом', () => {
    expect(STAGE_META_50['C50:WON'].kind).toBe('win');
    expect(STAGE_META_50['C50:APOLOGY'].kind).toBe('lose');
    expect(STAGE_META_50['C50:NEW'].kind).toBe('open');
  });
});

describe('buildTmKpis', () => {
  it('суммирует отдел и считает производные (Исаева+Вострецов, май)', () => {
    const k = buildTmKpis([isaeva, vostretsov], 19);
    expect(k.zvonari).toBe(2);
    expect(k.dials).toBe(2556);
    expect(k.calls60).toBe(589);
    expect(k.meetingsSet).toBe(28);
    expect(k.answered).toBe(1620);
    expect(k.answerPct).toBeCloseTo(63.4, 0); // 1620/2556
    expect(k.convDialToMeeting).toBeCloseTo(4.8, 1); // 28/589
    expect(k.meetingsHeld).toBe(23); // состоялось по создателю 12+11
    expect(k.heldPct).toBeCloseTo(82.1, 0); // 23/28
    expect(k.talkHours).toBeCloseTo(25.7, 1);
    expect(k.dialsPerDay).toBe(Math.round(2556 / 19));
  });
  it('не делит на ноль на пустом вводе', () => {
    const k = buildTmKpis([], 1);
    expect(k.zvonari).toBe(0);
    expect(k.answerPct).toBeNull();
    expect(k.convDialToMeeting).toBeNull();
    expect(k.dialsPerZvonar).toBe(0);
  });
});

describe('buildTmManagerTable', () => {
  it('сортирует по наборам, считает % дозвона/конверсию и несёт должность', () => {
    const rows = buildTmManagerTable([vostretsov, isaeva]);
    expect(rows[0].name).toBe('Дарья Исаева'); // 1336 > 1220
    expect(rows[0].dept).toBe('Телемаркетолог');
    expect(rows[0].convDialToMeeting).toBeCloseTo(3.8, 1); // 14/370
    expect(rows[1].convDialToMeeting).toBeCloseTo(6.4, 1); // 14/219
    expect(rows[0].answerPct).toBeCloseTo(69.5, 0);
    expect(rows[0].meetingsHeld).toBe(12); // состоялось по создателю
    expect(rows[0].heldPct).toBeCloseTo(85.7, 0); // 12/14
  });
});

describe('buildTmMicroFunnel', () => {
  it('строит шаги набрал→снято→дозвон→встреча с % потерь', () => {
    const f = buildTmMicroFunnel(isaeva);
    expect(f.steps.map((s) => s.value)).toEqual([1336, 928, 370, 14]);
    expect(f.steps[0].pctFromPrev).toBeNull();
    expect(f.steps[1].pctFromPrev).toBeCloseTo(69.5, 0); // 928/1336
    expect(f.steps[3].pctFromPrev).toBeCloseTo(3.8, 1); // 14/370
    expect(f.burn).toBeCloseTo(5.5, 1); // отвал 77 / 14 встреч
    expect(buildTmMicroFunnel(vostretsov).burn).toBeCloseTo(16.9, 1); // 236 / 14
  });
});

describe('buildTmFunnel50', () => {
  it('считает по стадиям в порядке воронки и игнорирует чужие коды', () => {
    const cells = [
      { stage: 'C50:NEW' }, { stage: 'C50:NEW' }, { stage: 'C50:WON' },
      { stage: 'C50:APOLOGY' }, { stage: 'C10:NEW' /* чужая */ },
    ];
    const f = buildTmFunnel50(cells);
    expect(f[0].label).toBe('База');
    const byLabel = Object.fromEntries(f.map((s) => [s.label, s.count]));
    expect(byLabel['К обзвону']).toBe(2);
    expect(byLabel['Успех']).toBe(1);
    expect(byLabel['Отвал']).toBe(1);
    expect(f.reduce((a, s) => a + s.count, 0)).toBe(4); // C10:NEW не учтён
  });
});

describe('buildTmMonthly', () => {
  it('добавляет производные answerPct/talkMin/conv', () => {
    const rows = buildTmMonthly([
      { ym: '2026-05', label: 'май 26', dials: 1336, answered: 928, calls60: 370, talkSeconds: 904 * 60, meetingsSet: 14, meetingsHeldByCreator: 12, rejected: 77, postponed: 33 },
    ]);
    expect(rows[0].talkMin).toBe(904);
    expect(rows[0].conv).toBeCloseTo(3.8, 1);
    expect(rows[0].answerPct).toBeCloseTo(69.5, 0);
  });
});

describe('buildTmMeetingsResult', () => {
  it('считает явку и передачу в Продажи', () => {
    const r = buildTmMeetingsResult([{ ...isaeva, dealsCold: 3 }, { ...vostretsov, dealsCold: 2 }]);
    expect(r.set).toBe(28);
    expect(r.held).toBe(23);
    expect(r.heldPct).toBeCloseTo(82.1, 0);
    expect(r.toCold).toBe(5);
  });
});

describe('buildTmPlanFact', () => {
  const input = {
    dials60PerTm: 400,
    briefingsPerTm: 20,
    members: [
      { managerId: 2832, name: 'Вострецов Аркадий', calls60: 56, briefingsHeld: 6 },
      { managerId: 2772, name: 'Исаева Дарья', calls60: 69, briefingsHeld: 5 },
    ],
  };
  it('дозвоны и брифования: по звонарям + командно', () => {
    const pf = buildTmPlanFact(input);
    // дозвоны: команда 125 / план 800 (400×2); сортировка по факту (Исаева 69 первой)
    expect(pf.dials60.teamFact).toBe(125);
    expect(pf.dials60.teamPlan).toBe(800);
    expect(pf.dials60.perTm).toBe(400);
    expect(pf.dials60.managers[0].name).toBe('Исаева Дарья');
    // брифования: команда 11 / план 40
    expect(pf.briefings.teamFact).toBe(11);
    expect(pf.briefings.teamPlan).toBe(40);
    expect(pf.briefings.managers[0].fact).toBe(6); // Вострецов первым (6>5)
  });
  it('без звонарей — нулевые итоги, пустые списки', () => {
    const pf = buildTmPlanFact({ dials60PerTm: 400, briefingsPerTm: 20, members: [] });
    expect(pf.dials60.teamFact).toBe(0);
    expect(pf.dials60.teamPlan).toBe(0);
    expect(pf.dials60.managers).toHaveLength(0);
  });
});

describe('buildTmRejections', () => {
  it('группирует причины по звонарю, считает % и сортирует по убыванию', () => {
    const rows = buildTmRejections([
      { managerId: 2772, name: 'Дарья Исаева', reasonId: 8540, count: 127 }, // Все устраивает
      { managerId: 2772, name: 'Дарья Исаева', reasonId: 8546, count: 100 }, // Не вышли на ЛПР
      { managerId: 2772, name: 'Дарья Исаева', reasonId: null, count: 7 }, // не указана
      { managerId: 2832, name: 'Аркадий Вострецов', reasonId: 8540, count: 300 },
    ]);
    const darya = rows.find((r) => r.managerId === 2772)!;
    expect(rows[0].managerId).toBe(2832); // 300 > 234
    expect(darya.total).toBe(234);
    expect(darya.reasons[0].label).toBe('Все устраивает');
    expect(darya.reasons[0].pct).toBe(Math.round((127 / 234) * 100));
    expect(darya.reasons.find((b) => b.reasonId === null)!.label).toBe('(не указана)');
  });
});

describe('buildTmMeetingQuality', () => {
  it('бьёт по баллам содержательные/слабые/пустые + по звонарю', () => {
    const q = buildTmMeetingQuality([
      { managerId: 2772, name: 'Дарья Исаева', score: 8, hasNextStep: true },
      { managerId: 2772, name: 'Дарья Исаева', score: 5, hasNextStep: false },
      { managerId: 2832, name: 'Аркадий Вострецов', score: 9, hasNextStep: true },
      { managerId: 2832, name: 'Аркадий Вострецов', score: 2, hasNextStep: false },
    ]);
    expect(q.total).toBe(4);
    expect(q.rich).toBe(2); // 8, 9
    expect(q.weak).toBe(1); // 5
    expect(q.empty).toBe(1); // 2
    expect(q.richPct).toBe(50);
    expect(q.nextStepPct).toBe(50);
    expect(q.byManager.find((m) => m.managerId === 2772)!.richPct).toBe(50); // 1 из 2
  });
});

describe('buildTmAlerts', () => {
  it('ловит просадку/рост конверсии, сжигание базы и низкую явку', () => {
    const a = buildTmAlerts([
      { name: 'Дарья', convNow: 3.8, convPrev: 9.4, burn: 5, heldPct: 80 }, // просадка
      { name: 'Аркадий', convNow: 6.4, convPrev: 5.1, burn: 16.9, heldPct: 73 }, // burn высокий
      { name: 'Петя', convNow: 8, convPrev: 8, burn: 2, heldPct: 40 }, // низкая явка
    ]);
    expect(a.some((x) => x.level === 'red' && x.title.includes('Дарья'))).toBe(true);
    expect(a.some((x) => x.icon === '🔥' && x.title.includes('Аркадий'))).toBe(true);
    expect(a.some((x) => x.title.includes('Низкая явка') && x.title.includes('Петя'))).toBe(true);
  });
  it('тихо при норме', () => {
    expect(buildTmAlerts([{ name: 'X', convNow: 8, convPrev: 8, burn: 3, heldPct: 80 }])).toHaveLength(0);
  });
});

describe('buildTmHeatmap', () => {
  it('строит сетку Пн–Пт × часы, считает % дозвона и игнорирует выходные', () => {
    const h = buildTmHeatmap([
      { dow: 1, hour: 9, dials: 10, calls60: 4 }, // Пн 9:00 → 40%
      { dow: 1, hour: 13, dials: 10, calls60: 1 }, // Пн 13:00 → 10%
      { dow: 5, hour: 9, dials: 5, calls60: 3 }, // Пт 9:00 → 60%
      { dow: 0, hour: 9, dials: 99, calls60: 99 }, // Вс — игнор
    ]);
    expect(h.hours).toEqual([9, 13]);
    expect(h.rows).toHaveLength(5); // Пн–Пт
    const mon = h.rows.find((r) => r.dow === 1)!;
    expect(mon.label).toBe('Пн');
    expect(mon.cells.find((c) => c.hour === 9)!.pct).toBe(40);
    expect(mon.cells.find((c) => c.hour === 13)!.pct).toBe(10);
    expect(h.maxPct).toBe(60); // Пт 9:00
    const wed = h.rows.find((r) => r.dow === 3)!; // нет данных
    expect(wed.cells.every((c) => c.pct === null)).toBe(true);
  });
});

describe('buildTmOutreach', () => {
  it('суммирует, отбрасывает нулевые строки и считает касаний на встречу', () => {
    const o = buildTmOutreach([
      { ...isaeva, messenger: 10, emails: 4 }, // meetingsSet 14
      { ...vostretsov, messenger: 0, emails: 0 }, // meetingsSet 14
    ]);
    expect(o.messengerTotal).toBe(10);
    expect(o.emailTotal).toBe(4);
    expect(o.rows).toHaveLength(1);
    expect(o.perMeeting).toBeCloseTo(0.5, 1); // (10+4)/28
  });
});
