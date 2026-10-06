/** UI «по Вт, Чт» ⇄ RRULE. Поддерживаем только то, что умеет UI: еженедельно по дням. */

const CODES = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
const SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

/** ISO-дни (1 = Пн) → RRULE. */
export function weekdaysToRrule(days: number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (sorted.length === 7) return 'FREQ=DAILY'
  return `FREQ=WEEKLY;BYDAY=${sorted.map((d) => CODES[d - 1]).join(',')}`
}

/** RRULE → ISO-дни, если правило из тех, что умеет UI; иначе null. */
export function rruleToWeekdays(rrule: string): number[] | null {
  const parts = Object.fromEntries(
    rrule
      .replace(/^RRULE:/, '')
      .split(';')
      .map((p) => p.split('=') as [string, string]),
  )
  if (parts.FREQ === 'DAILY' && Object.keys(parts).length === 1) return [1, 2, 3, 4, 5, 6, 7]
  if (parts.FREQ !== 'WEEKLY' || !parts.BYDAY) return null
  if (Object.keys(parts).some((k) => !['FREQ', 'BYDAY'].includes(k))) return null
  const days = parts.BYDAY.split(',').map((c: string) => CODES.indexOf(c) + 1)
  return days.every((d: number) => d > 0) ? days.sort((a: number, b: number) => a - b) : null
}

/** «по вт, чт», «каждый день», или сам RRULE, если UI его не понимает. */
export function describeRrule(rrule: string): string {
  const days = rruleToWeekdays(rrule)
  if (!days) return rrule
  if (days.length === 7) return 'каждый день'
  if (days.join() === '1,2,3,4,5') return 'по будням'
  return `по ${days.map((d) => SHORT[d - 1]).join(', ')}`
}
