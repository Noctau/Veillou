import { SCHEDULE_UI as T } from '@/lib/terms'
import { formatDay } from '@/lib/time'

import type { Area } from '@/features/areas/useAreas'

import type { EventType, Pattern, ScheduleRule } from './useSchedule'

const SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

/** «по вт, чт», «по будням · неделя 1», «2 через 2 с 12 окт», «20 окт», или сам RRULE. */
export function describePattern(pattern: Pattern): string {
  switch (pattern.kind) {
    case 'weekly': {
      const days = pattern.weekdays
      const what =
        days.length === 7
          ? 'каждый день'
          : days.join() === '1,2,3,4,5'
            ? 'по будням'
            : `по ${days.map((d) => SHORT[d - 1]).join(', ')}`
      const weeks = pattern.cycle_weeks?.length ? ` · ${pattern.cycle_weeks.map(T.cycleWeek).join(', ').toLowerCase()}` : ''
      return what + weeks
    }
    case 'day_cycle':
      return `${pattern.on} через ${pattern.off} с ${formatDay(pattern.anchor)}`
    case 'once':
      return formatDay(pattern.date)
    case 'rrule':
      return pattern.rrule
  }
}

/** Идёт ли правило по дням недели в этот день недели и неделю цикла (для сетки недели). */
export function onWeekCell(rule: ScheduleRule, weekday: number, cycleWeek: number): boolean {
  const p = rule.pattern
  if (p.kind !== 'weekly' || !p.weekdays.includes(weekday)) return false
  return !p.cycle_weeks?.length || p.cycle_weeks.includes(cycleWeek)
}

/** «HH:MM» → минуты от полуночи. */
export function minutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

/** Подпись правила: своё название → короткое имя сферы → сфера → тип занятости. */
export function ruleLabel(rule: ScheduleRule, area?: Area, type?: EventType): string {
  return rule.title || area?.short_name || area?.name || type?.name || '—'
}
