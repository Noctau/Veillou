import { describe, expect, it } from 'vitest'

import { describeRrule, rruleToWeekdays, weekdaysToRrule } from './rrule'

describe('rrule', () => {
  it('дни недели ⇄ RRULE', () => {
    expect(weekdaysToRrule([4, 2, 2])).toBe('FREQ=WEEKLY;BYDAY=TU,TH')
    expect(weekdaysToRrule([1, 2, 3, 4, 5, 6, 7])).toBe('FREQ=DAILY')
    expect(rruleToWeekdays('RRULE:FREQ=WEEKLY;BYDAY=TH,TU')).toEqual([2, 4])
    expect(rruleToWeekdays('FREQ=DAILY')).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('чужие правила UI не понимает', () => {
    expect(rruleToWeekdays('FREQ=MONTHLY;BYMONTHDAY=1')).toBeNull()
    expect(rruleToWeekdays('FREQ=WEEKLY;BYDAY=TU;INTERVAL=2')).toBeNull()
    expect(rruleToWeekdays('FREQ=WEEKLY;BYDAY=XX')).toBeNull()
  })

  it('описание', () => {
    expect(describeRrule('FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR')).toBe('по будням')
    expect(describeRrule('FREQ=WEEKLY;BYDAY=TU,TH')).toBe('по вт, чт')
    expect(describeRrule('FREQ=DAILY')).toBe('каждый день')
    expect(describeRrule('FREQ=MONTHLY')).toBe('FREQ=MONTHLY')
  })
})
