import { describe, expect, it } from 'vitest'

import { describePattern, onWeekCell } from './pattern'
import type { ScheduleRule } from './useSchedule'

const rule = (pattern: ScheduleRule['pattern']) => ({ pattern }) as ScheduleRule

describe('describePattern', () => {
  it('дни недели и недели цикла', () => {
    expect(describePattern({ kind: 'weekly', weekdays: [2, 4], cycle_weeks: null })).toBe('по вт, чт')
    expect(describePattern({ kind: 'weekly', weekdays: [1, 2, 3, 4, 5], cycle_weeks: [1] })).toBe('по будням · неделя 1')
    expect(describePattern({ kind: 'weekly', weekdays: [1, 2, 3, 4, 5, 6, 7], cycle_weeks: null })).toBe('каждый день')
  })

  it('смены, разово, RRULE', () => {
    expect(describePattern({ kind: 'day_cycle', on: 2, off: 2, anchor: '2026-10-12' })).toMatch(/^2 через 2 с /)
    expect(describePattern({ kind: 'rrule', rrule: 'FREQ=MONTHLY;BYDAY=2TU' })).toBe('FREQ=MONTHLY;BYDAY=2TU')
  })
})

describe('onWeekCell', () => {
  it('маска недель цикла', () => {
    const odd = rule({ kind: 'weekly', weekdays: [1], cycle_weeks: [1] })
    expect(onWeekCell(odd, 1, 1)).toBe(true)
    expect(onWeekCell(odd, 1, 2)).toBe(false)
    expect(onWeekCell(odd, 2, 1)).toBe(false)
    expect(onWeekCell(rule({ kind: 'weekly', weekdays: [1], cycle_weeks: null }), 1, 2)).toBe(true)
    expect(onWeekCell(rule({ kind: 'once', date: '2026-10-20' }), 2, 1)).toBe(false)
  })
})
