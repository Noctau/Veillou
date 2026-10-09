import { describe, expect, it } from 'vitest'

import type { Milestone } from './useProjects'
import { buildTimeline, MONTH_W, shortTitle } from './timeline'

function ms(title: string, date: string | null, status = 'planned'): Milestone {
  return { id: title, title, date, status } as unknown as Milestone
}

describe('таймлайн проекта', () => {
  it('шкала от сегодня до срока, минимум 4 месяца', () => {
    const t = buildTimeline([], null, '2026-10-08')
    expect(t.months.map((m) => m.label)).toEqual(['окт', 'ноя', 'дек', 'янв'])
    expect(t.months[0].year).toBe('2026')
    expect(t.months[3].year).toBe('2027') // январь подписан годом
    expect(t.width).toBe(4 * MONTH_W)
  })

  it('просроченный этап и отставание до сегодня', () => {
    const t = buildTimeline(
      [ms('A', '2026-09-15'), ms('B', '2026-11-01'), ms('C', null), ms('D', '2026-09-01', 'done')],
      '2027-05-30',
      '2026-10-08',
    )
    expect(t.points.map((p) => [p.milestone.title, p.state])).toEqual([
      ['D', 'done'],
      ['A', 'late'],
      ['B', 'planned'],
    ])
    expect(t.lag).toEqual({ from: t.points[1].x, to: t.todayX })
    expect(t.undated).toBe(1)
    expect(t.deadlineX).toBeGreaterThan(t.todayX)
  })

  it('короткая подпись', () => {
    expect(shortTitle('Обзор литературы готов')).toBe('Обзор литерат…')
    expect(shortTitle('Защита')).toBe('Защита')
  })
})
