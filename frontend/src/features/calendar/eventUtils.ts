import { CLASS_TYPE_LABEL } from '@/features/schedule/parity'
import { KIND_COLORS } from '@/lib/colors'
import { wallTime } from '@/lib/time'

import type { CalendarEvent, EventKind } from './useCalendar'

export const KIND_LABEL: Record<EventKind, string> = {
  class: 'Пары',
  personal: 'Личное',
  rest: 'Отдых',
  subtask: 'Задания',
  backlog: 'Ящик',
  exam_prep: 'Подготовка',
  exam: 'Экзамены',
  project: 'Проекты',
}

/** Тип одного события — для карточки. */
export const KIND_SINGLE: Record<EventKind, string> = {
  class: 'Пара',
  personal: 'Личное',
  rest: 'Отдых',
  subtask: 'Подзадача',
  backlog: 'Дело из ящика',
  exam_prep: 'Подготовка к экзамену',
  exam: 'Экзамен',
  project: 'Работа над проектом',
}

/** То, что отмечают «сделано» и что входит в прогресс дня (пары и отдых — нет). */
export const DOABLE_KINDS: ReadonlySet<EventKind> = new Set(['personal', 'subtask', 'backlog', 'exam_prep', 'project'])

export function isDoable(e: CalendarEvent): boolean {
  return DOABLE_KINDS.has(e.kind) && e.status !== 'cancelled'
}

export function eventColor(e: CalendarEvent): string {
  return e.color ?? KIND_COLORS[e.kind]
}

export function timeRange(e: CalendarEvent, tz: string): string {
  return `${wallTime(e.start, tz)}–${wallTime(e.end, tz)}`
}

/** «Семинар · 1801 · Иванова» */
export function classDetails(e: CalendarEvent): string {
  return [e.class_type && CLASS_TYPE_LABEL[e.class_type], e.location, e.teacher]
    .filter(Boolean)
    .join(' · ')
}
