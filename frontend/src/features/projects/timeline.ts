import { addMonths, differenceInCalendarDays, endOfMonth, format, parseISO, startOfMonth } from 'date-fns'

import type { Milestone } from './useProjects'

/** Ширина месяца на шкале, px. */
export const MONTH_W = 64
const MIN_MONTHS = 4

export type TimelineMonth = { x: number; label: string; year: string | null }
export type TimelinePoint = {
  milestone: Milestone
  x: number
  state: 'done' | 'late' | 'planned'
  /** Три высоты подписей по кругу — соседние не налезают друг на друга. */
  row: 0 | 1 | 2
}

export type Timeline = {
  width: number
  months: TimelineMonth[]
  points: TimelinePoint[]
  todayX: number
  deadlineX: number | null
  /** Отставание: от самого старого просроченного этапа до сегодня. */
  lag: { from: number; to: number } | null
  undated: number
}

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

/**
 * Геометрия таймлайна проекта: шкала месяцев от самого раннего из
 * «сегодня / первый этап» до самого позднего из «итоговый срок / последний этап».
 */
export function buildTimeline(milestones: Milestone[], deadline: string | null, today: string): Timeline {
  const dated = milestones.filter((m) => m.date).sort((a, b) => a.date!.localeCompare(b.date!))
  const days = [today, ...dated.map((m) => m.date!), ...(deadline ? [deadline] : [])].sort()
  const start = startOfMonth(parseISO(days[0]))
  let end = endOfMonth(parseISO(days[days.length - 1]))
  if (differenceInCalendarDays(end, start) < MIN_MONTHS * 30) end = endOfMonth(addMonths(start, MIN_MONTHS - 1))

  const months: TimelineMonth[] = []
  for (let m = start, i = 0; m <= end; m = addMonths(m, 1), i++) {
    const first = i === 0 || m.getMonth() === 0
    months.push({
      x: i * MONTH_W,
      label: MONTHS[m.getMonth()],
      year: first ? format(m, 'yyyy') : null,
    })
  }

  // Внутри месяца — пропорционально дню
  const x = (day: string) => {
    const d = parseISO(day)
    const i = (d.getFullYear() - start.getFullYear()) * 12 + d.getMonth() - start.getMonth()
    const len = differenceInCalendarDays(endOfMonth(d), startOfMonth(d)) + 1
    return i * MONTH_W + ((d.getDate() - 0.5) / len) * MONTH_W
  }

  const points: TimelinePoint[] = dated.map((m, i) => ({
    milestone: m,
    x: x(m.date!),
    state: m.status === 'done' ? 'done' : m.date! < today ? 'late' : 'planned',
    row: (i % 3) as 0 | 1 | 2,
  }))
  const firstLate = points.find((p) => p.state === 'late')
  const todayX = x(today)
  return {
    width: months.length * MONTH_W,
    months,
    points,
    todayX,
    deadlineX: deadline ? x(deadline) : null,
    lag: firstLate ? { from: firstLate.x, to: todayX } : null,
    undated: milestones.length - dated.length,
  }
}

/** Подпись этапа на шкале — коротко, полное название во всплывающей подсказке. */
export function shortTitle(title: string, max = 14): string {
  return title.length > max ? `${title.slice(0, max - 1).trimEnd()}…` : title
}
