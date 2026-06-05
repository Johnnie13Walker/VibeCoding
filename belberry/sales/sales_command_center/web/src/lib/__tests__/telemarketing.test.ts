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
  type TmMember,
} from '@/lib/telemarketing-shared';

// Реальные числа из отчёта ТМ (май 2026) — фиксируем расчёт на достоверных данных.
const isaeva: TmMember = {
  managerId: 2772, name: 'Дарья Исаева',
  dials: 1336, answered: 928, calls60: 370, calls120: 0, talkSeconds: 904 * 60,
  meetingsSet: 14, meetingsHeld: 12, dealsCold: 0, messenger: 0, emails: 0,
};
const vostretsov: TmMember = {
  managerId: 2832, name: 'Аркадий Вострецов',
  dials: 1220, answered: 692, calls60: 219, calls120: 0, talkSeconds: 637 * 60,
  meetingsSet: 14, meetingsHeld: 11, dealsCold: 0, messenger: 0, emails: 0,
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
  it('сортирует по наборам и считает % дозвона/конверсию', () => {
    const rows = buildTmManagerTable([vostretsov, isaeva]);
    expect(rows[0].name).toBe('Дарья Исаева'); // 1336 > 1220
    expect(rows[0].convDialToMeeting).toBeCloseTo(3.8, 1); // 14/370
    expect(rows[1].convDialToMeeting).toBeCloseTo(6.4, 1); // 14/219
    expect(rows[0].answerPct).toBeCloseTo(69.5, 0);
  });
});

describe('buildTmMicroFunnel', () => {
  it('строит шаги набрал→снято→дозвон→встреча с % потерь', () => {
    const f = buildTmMicroFunnel(isaeva);
    expect(f.steps.map((s) => s.value)).toEqual([1336, 928, 370, 14]);
    expect(f.steps[0].pctFromPrev).toBeNull();
    expect(f.steps[1].pctFromPrev).toBeCloseTo(69.5, 0); // 928/1336
    expect(f.steps[3].pctFromPrev).toBeCloseTo(3.8, 1); // 14/370
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
      { ym: '2026-05', label: 'май 26', dials: 1336, answered: 928, calls60: 370, talkSeconds: 904 * 60, meetingsSet: 14, meetingsHeld: 12 },
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
  it('строит план встреч на всех ТМ и % выполнения', () => {
    const rows = buildTmPlanFact({ meetingsSetFact: 28, meetingsPlanPerTm: 20, tmCount: 2 });
    expect(rows).toHaveLength(1);
    expect(rows[0].plan).toBe(40); // 20 × 2
    expect(rows[0].pct).toBe(70); // 28/40
  });
  it('пустой результат без плана', () => {
    expect(buildTmPlanFact({ meetingsSetFact: 28, meetingsPlanPerTm: 0, tmCount: 2 })).toHaveLength(0);
  });
});

describe('buildTmOutreach', () => {
  it('суммирует и отбрасывает нулевые строки', () => {
    const o = buildTmOutreach([
      { ...isaeva, messenger: 10, emails: 4 },
      { ...vostretsov, messenger: 0, emails: 0 },
    ]);
    expect(o.messengerTotal).toBe(10);
    expect(o.emailTotal).toBe(4);
    expect(o.rows).toHaveLength(1);
  });
});
