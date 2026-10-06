import { differenceInCalendarDays, parseISO } from 'date-fns'

import { weekMonday } from '@/lib/time'

import type { ClassType, Parity, RuleParity } from './useSchedule'

/** Чётность недели дня — так же, как на бэкенде (domain/recurrence.week_parity). */
export function weekParity(day: string, semesterStart: string, first: Parity): Parity {
  const weeks = differenceInCalendarDays(parseISO(weekMonday(day)), parseISO(weekMonday(semesterStart))) / 7
  if (Math.abs(weeks) % 2 === 0) return first
  return first === 'odd' ? 'even' : 'odd'
}

export const PARITY_LABEL: Record<Parity, string> = { odd: 'Числитель', even: 'Знаменатель' }

export const RULE_PARITY_LABEL: Record<RuleParity, string> = {
  all: 'Каждую неделю',
  odd: 'Числитель',
  even: 'Знаменатель',
}

export const CLASS_TYPE_LABEL: Record<ClassType, string> = {
  lecture: 'Лекция',
  seminar: 'Семинар',
  lab: 'Лаба',
  other: 'Другое',
}

export function oppositeParity(p: Parity): Parity {
  return p === 'odd' ? 'even' : 'odd'
}

/** Звонки МГУ по умолчанию — правятся в настройках семестра. */
export const DEFAULT_BELLS = [
  { number: 1, start: '09:00', end: '10:35' },
  { number: 2, start: '10:50', end: '12:25' },
  { number: 3, start: '13:00', end: '14:35' },
  { number: 4, start: '14:50', end: '16:25' },
  { number: 5, start: '16:40', end: '18:15' },
  { number: 6, start: '18:30', end: '20:05' },
]
