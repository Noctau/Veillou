import { describe, expect, it } from 'vitest'

import { oppositeParity, weekParity } from './parity'

describe('weekParity — как domain/recurrence.week_parity на бэкенде', () => {
  it('неделя начала семестра получает первую чётность, дальше — чередование', () => {
    expect(weekParity('2026-09-03', '2026-09-01', 'odd')).toBe('odd')
    expect(weekParity('2026-09-07', '2026-09-01', 'odd')).toBe('even')
    expect(weekParity('2026-09-14', '2026-09-01', 'odd')).toBe('odd')
  })

  it('через Новый год — по неделям от начала, а не по номерам ISO', () => {
    // 2026-12-28 и 2027-01-04 — соседние понедельники
    const a = weekParity('2026-12-28', '2026-09-01', 'even')
    expect(weekParity('2027-01-04', '2026-09-01', 'even')).toBe(oppositeParity(a))
  })
})
