import { describe, expect, it } from 'vitest'

import { addDaysIso, dayStartUtc, isoWeekday, todayIn, wallTime, wallToUtc, weekMonday } from './time'

describe('время в TZ пользователя', () => {
  it('дни недели и понедельник', () => {
    expect(isoWeekday('2026-10-11')).toBe(7)
    expect(weekMonday('2026-10-11')).toBe('2026-10-05')
    expect(addDaysIso('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('настенное время ⇄ UTC', () => {
    expect(wallToUtc('2026-10-08', '09:00', 'Europe/Moscow')).toBe('2026-10-08T06:00:00.000Z')
    expect(wallTime('2026-10-08T06:00:00Z', 'Europe/Moscow')).toBe('09:00')
    expect(dayStartUtc('2026-10-08', 'Europe/Moscow')).toBe('2026-10-07T21:00:00.000Z')
  })

  it('переход на летнее время (Берлин)', () => {
    expect(wallToUtc('2026-03-29', '12:00', 'Europe/Berlin')).toBe('2026-03-29T10:00:00.000Z')
    expect(wallToUtc('2026-03-28', '12:00', 'Europe/Berlin')).toBe('2026-03-28T11:00:00.000Z')
  })

  it('«сегодня» — по TZ, а не по UTC', () => {
    const lateEvening = new Date('2026-10-08T22:30:00Z')
    expect(todayIn('Europe/Moscow', lateEvening)).toBe('2026-10-09')
    expect(todayIn('UTC', lateEvening)).toBe('2026-10-08')
  })
})
