import { describe, expect, it } from 'vitest';

import { buildManagerScores, type MeetingItem } from '../meetings-shared';

function mk(p: Partial<MeetingItem>): MeetingItem {
  return {
    id: 1, date: '2026-06-02', time: '12:00', managerId: 1, manager: 'А', type: 'briefing',
    domain: 'x.ru', dealId: 1, score: 7, good: [], risk: [], verdict: '', conclusion: '',
    nextStep: { what: 'x' }, transcript: 'ok', summarySent: null, budgetNamed: null, ...p,
  };
}

describe('buildManagerScores', () => {
  it('средний балл, разрез брифинг/защита, % итогов и пробелы транскрипта', () => {
    const s = buildManagerScores([
      mk({ managerId: 1, manager: 'А', type: 'briefing', score: 8, summarySent: true, nextStep: { what: 'a' } }),
      mk({ managerId: 1, manager: 'А', type: 'defense', score: 6, summarySent: false, nextStep: null }),
      mk({ managerId: 1, manager: 'А', type: 'briefing', score: null, transcript: 'no_transcript', summarySent: null, nextStep: null }),
      mk({ managerId: 2, manager: 'Б', type: 'briefing', score: 4, summarySent: false }),
    ]);
    const a = s.find((x) => x.managerId === 1)!;
    expect(a.count).toBe(3);
    expect(a.avg).toBe(7); // (8+6)/2
    expect(a.briefingAvg).toBe(8); // только разобранный брифинг (8)
    expect(a.defenseAvg).toBe(6);
    expect(a.summaryPct).toBe(50); // из 2 известных (true/false)
    expect(a.nextStepPct).toBe(33); // 1 из 3
    expect(a.gaps).toBe(1);
    // сортировка по среднему баллу убыв.: А (7) перед Б (4)
    expect(s[0].managerId).toBe(1);
  });

  it('нет разобранных — avg null, % итогов null без known', () => {
    const s = buildManagerScores([mk({ score: null, summarySent: null, transcript: 'no_transcript' })]);
    expect(s[0].avg).toBeNull();
    expect(s[0].summaryPct).toBeNull();
  });
});
