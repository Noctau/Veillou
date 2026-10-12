import { differenceInCalendarDays, parseISO } from 'date-fns'

import { formatDay, wallDate, wallTime } from '@/lib/time'

/** 90 → «1 ч 30 мин», 30 → «30 мин». */
export function formatMinutes(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (!h) return `${m} мин`
  return m ? `${h} ч ${m} мин` : `${h} ч`
}

export type DeadlineInfo = { text: string; tone: 'overdue' | 'soon' | 'normal' }

/** «сегодня до 18:00», «завтра», «через 3 дн.», «просрочено», «15 окт., чт». */
export function describeDeadline(deadline: string, tz: string, now: Date = new Date()): DeadlineInfo {
  const at = parseISO(deadline)
  const days = differenceInCalendarDays(parseISO(wallDate(deadline, tz)), parseISO(wallDate(now.toISOString(), tz)))
  const time = wallTime(deadline, tz)
  const timeSuffix = time === '23:59' ? '' : ` до ${time}`
  if (at < now) return { text: days === 0 ? `просрочено${timeSuffix && ` (${time})`}` : 'просрочено', tone: 'overdue' }
  if (days === 0) return { text: `сегодня${timeSuffix}`, tone: 'soon' }
  if (days === 1) return { text: `завтра${timeSuffix}`, tone: 'soon' }
  if (days <= 6) return { text: `через ${days} дн.`, tone: days <= 3 ? 'soon' : 'normal' }
  return { text: formatDay(wallDate(deadline, tz)), tone: 'normal' }
}
