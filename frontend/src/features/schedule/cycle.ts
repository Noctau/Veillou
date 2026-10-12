import { differenceInCalendarDays, parseISO } from 'date-fns'

import { weekMonday } from '@/lib/time'

type CyclePeriod = { start_date: string; cycle_weeks: number; first_cycle_week: number }

/** Неделя цикла дня (1…cycle_weeks) — так же, как на бэкенде (domain/recurrence.cycle_week). */
export function cycleWeek(day: string, period: CyclePeriod): number {
  if (period.cycle_weeks <= 1) return 1
  const weeks = differenceInCalendarDays(parseISO(weekMonday(day)), parseISO(weekMonday(period.start_date))) / 7
  const n = (period.first_cycle_week - 1 + weeks) % period.cycle_weeks
  return (n + period.cycle_weeks) % period.cycle_weeks + 1
}

/** Слоты по умолчанию для новой сетки — правятся в настройках периода. */
export const DEFAULT_SLOTS = [
  { number: 1, start: '09:00', end: '10:35' },
  { number: 2, start: '10:50', end: '12:25' },
  { number: 3, start: '13:00', end: '14:35' },
  { number: 4, start: '14:50', end: '16:25' },
  { number: 5, start: '16:40', end: '18:15' },
  { number: 6, start: '18:30', end: '20:05' },
]
