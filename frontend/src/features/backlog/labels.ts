import { differenceInCalendarDays, parseISO } from 'date-fns'

import type { BacklogCondition } from './useBacklog'

export const CONDITION_LABEL: Record<BacklogCondition, string> = {
  weekday_daytime: 'В будни днём',
  on_class_days: 'В дни пар',
  needs_laptop: 'Нужен ноутбук',
  institution_hours: 'Часы учреждений',
}

export const CONDITIONS = Object.keys(CONDITION_LABEL) as BacklogCondition[]

export const ESTIMATES = [
  { value: 15, label: '15 мин' },
  { value: 60, label: '1 ч' },
  { value: 240, label: 'полдня' },
] as const

export function estimateLabel(min: number | null): string | null {
  if (min == null) return null
  return ESTIMATES.find((e) => e.value === min)?.label ?? `${min} мин`
}

/** Сколько дело лежит: «сегодня», «5 дн.», «3 нед.», «2 мес.». */
export function ageLabel(createdAt: string, now: Date = new Date()): string {
  const days = differenceInCalendarDays(now, parseISO(createdAt))
  if (days <= 0) return 'сегодня'
  if (days < 14) return `${days} дн.`
  if (days < 60) return `${Math.floor(days / 7)} нед.`
  return `${Math.floor(days / 30)} мес.`
}
