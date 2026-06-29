import { describe, it, expect } from 'vitest';
import { sortByProblems, effLevel, type TeamMemberHealth } from '../team-health';

function m(over: Partial<TeamMemberHealth> & { managerId: number }): TeamMemberHealth {
  return {
    name: `m${over.managerId}`,
    dept: 'Менеджер по продажам',
    efficiencyPct: null,
    overdueTasks: 0,
    overdueActivities: 0,
    overdueTotal: 0,
    ...over,
  };
}

describe('sortByProblems', () => {
  it('ставит сначала тех, у кого больше просрочек', () => {
    const sorted = sortByProblems([
      m({ managerId: 1, overdueTotal: 3 }),
      m({ managerId: 2, overdueTotal: 15 }),
      m({ managerId: 3, overdueTotal: 0 }),
    ]);
    expect(sorted.map((x) => x.managerId)).toEqual([2, 1, 3]);
  });

  it('при равных просрочках — ниже КПД выше', () => {
    const sorted = sortByProblems([
      m({ managerId: 1, overdueTotal: 5, efficiencyPct: 90 }),
      m({ managerId: 2, overdueTotal: 5, efficiencyPct: 40 }),
    ]);
    expect(sorted.map((x) => x.managerId)).toEqual([2, 1]);
  });

  it('пустой КПД уходит вниз при равных просрочках', () => {
    const sorted = sortByProblems([
      m({ managerId: 1, overdueTotal: 0, efficiencyPct: null }),
      m({ managerId: 2, overdueTotal: 0, efficiencyPct: 50 }),
    ]);
    expect(sorted.map((x) => x.managerId)).toEqual([2, 1]);
  });

  it('не мутирует исходный массив', () => {
    const input = [m({ managerId: 1, overdueTotal: 1 }), m({ managerId: 2, overdueTotal: 9 })];
    const copy = [...input];
    sortByProblems(input);
    expect(input).toEqual(copy);
  });
});

describe('effLevel', () => {
  it('пороги good/warn/bad/unknown', () => {
    expect(effLevel(null)).toBe('unknown');
    expect(effLevel(95)).toBe('good');
    expect(effLevel(85)).toBe('good');
    expect(effLevel(70)).toBe('warn');
    expect(effLevel(60)).toBe('warn');
    expect(effLevel(59)).toBe('bad');
    expect(effLevel(0)).toBe('bad');
  });
});
