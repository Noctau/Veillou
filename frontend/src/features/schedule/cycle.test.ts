import { describe, expect, it } from 'vitest'

import { cycleWeek } from './cycle'

const FALL = { start_date: '2026-09-01', cycle_weeks: 2, first_cycle_week: 1 }

describe('cycleWeek — как domain/recurrence.cycle_week на бэкенде', () => {
  it('неделя начала периода — first_cycle_week, дальше по кругу', () => {
    expect(cycleWeek('2026-09-03', FALL)).toBe(1)
    expect(cycleWeek('2026-09-07', FALL)).toBe(2)
    expect(cycleWeek('2026-09-14', FALL)).toBe(1)
    expect(cycleWeek('2026-09-07', { ...FALL, first_cycle_week: 2 })).toBe(1)
  })

  it('через Новый год — по неделям от начала, а не по номерам ISO', () => {
    // 2026-12-28 и 2027-01-04 — соседние понедельники
    expect(cycleWeek('2026-12-28', FALL)).not.toBe(cycleWeek('2027-01-04', FALL))
  })

  it('цикл 3 недели и дни до начала периода', () => {
    const p = { start_date: '2026-09-01', cycle_weeks: 3, first_cycle_week: 1 }
    expect(['2026-09-01', '2026-09-08', '2026-09-15', '2026-09-22'].map((d) => cycleWeek(d, p))).toEqual([1, 2, 3, 1])
    expect(cycleWeek('2026-08-25', p)).toBe(3)
  })

  it('без цикла — всегда 1', () => {
    expect(cycleWeek('2026-10-20', { ...FALL, cycle_weeks: 1 })).toBe(1)
  })
})
