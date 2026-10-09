import { describe, expect, it } from 'vitest'

import { describeWeekdays, describeWindow, describeWindows, windowsValid } from './windows'

describe('windows', () => {
  it('дни недели', () => {
    expect(describeWeekdays([5, 1, 2, 3, 4])).toBe('пн–пт')
    expect(describeWeekdays([2, 4])).toBe('вт, чт')
    expect(describeWeekdays([1, 2, 3, 4, 5, 6, 7])).toBe('каждый день')
  })

  it('окно через полночь помечается', () => {
    expect(describeWindow({ weekdays: [6, 7], start: '22:00', end: '02:00' })).toBe('сб, вс 22:00–02:00 (до утра)')
    expect(describeWindows(null)).toBe('как у типа')
  })

  it('пустые дни и нулевая длина — невалидны', () => {
    expect(windowsValid([{ weekdays: [], start: '09:00', end: '10:00' }])).toBe(false)
    expect(windowsValid([{ weekdays: [1], start: '09:00', end: '09:00' }])).toBe(false)
    expect(windowsValid([{ weekdays: [1], start: '09:00', end: '10:00' }])).toBe(true)
  })
})
