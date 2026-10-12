import { useMemo } from 'react'

import { renderFields } from '@/features/areas/fields'
import { type EventType, useEventTypes } from '@/features/schedule/useSchedule'
import { KIND_COLORS } from '@/lib/colors'
import { wallTime } from '@/lib/time'

import type { CalendarEvent } from './useCalendar'

/** Блоки плана, которые отмечают «сделано» и что входит в прогресс дня. */
const FLEXIBLE_DOABLE = new Set(['subtask', 'backlog', 'prep', 'project'])

export function timeRange(e: CalendarEvent, tz: string): string {
  return `${wallTime(e.start, tz)}–${wallTime(e.end, tz)}`
}

/** Место с подписью типа: «каб. 12» / «Бассейн „Волна“». */
export function placeOf(e: CalendarEvent, type?: EventType): string | null {
  if (!e.location) return null
  return type?.location_label ? `${type.location_label} ${e.location}` : e.location
}

/**
 * Показ событий по справочнику типов занятости: цвет, строка деталей, тип.
 * Отмечать «сделано» можно блоки плана и жёсткие события, кроме отдыха и типов
 * с «Сейчас / Дальше» (их не «делают» — на них ходят).
 */
export function useEventView() {
  const { data } = useEventTypes()
  return useMemo(() => {
    const types = new Map((data ?? []).map((t) => [t.id, t]))
    const typeOf = (e: CalendarEvent) => (e.event_type_id ? types.get(e.event_type_id) : undefined)
    const isDoable = (e: CalendarEvent) => {
      if (e.status === 'cancelled') return false
      if (FLEXIBLE_DOABLE.has(e.kind)) return true
      const t = typeOf(e)
      return e.kind === 'busy' && (!t || (!t.is_rest && !t.show_now_next))
    }
    const color = (e: CalendarEvent) => e.color ?? typeOf(e)?.color ?? KIND_COLORS[e.kind]
    /** «практика · каб. 12 · Иванова» — поля «в напоминании» и место. */
    const details = (e: CalendarEvent, { withPlace = true } = {}) => {
      const t = typeOf(e)
      const fields = t ? renderFields(t.fields, e.fields, { onlyReminder: true }).map((f) => f.text) : []
      return [...fields, withPlace && placeOf(e, t)].filter(Boolean).join(' · ')
    }
    return { types, typeOf, isDoable, color, details }
  }, [data])
}

export type EventView = ReturnType<typeof useEventView>
