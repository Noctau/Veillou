import { type QueryClient, queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'
import { wallDate } from '@/lib/time'

export type CalendarEvent = components['schemas']['EventRead']
export type CalendarData = components['schemas']['CalendarRead']
export type EventCreate = components['schemas']['EventCreate']
export type EventUpdate = components['schemas']['EventUpdate']
export type EventKind = components['schemas']['EventKind']
export type EventStatus = components['schemas']['EventStatus']
export type RecurringEvent = components['schemas']['RecurringEventRead']
export type RecurringEventCreate = components['schemas']['RecurringEventCreate']
export type RecurringEventUpdate = components['schemas']['RecurringEventUpdate']

export function calendarQueryOptions(from: string, to: string) {
  return queryOptions({
    queryKey: queryKeys.calendar(from, to),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/calendar', { params: { query: { from, to } } })
      if (error) throw error
      return data
    },
  })
}

/**
 * Срез уже загруженного диапазона, который накрывает [from, to): день из загруженной
 * недели показывается сразу — и без сети (офлайн-окно грузит useOfflinePrefetch).
 */
function cachedSubrange(queryClient: QueryClient, from: string, to: string, tz: string): CalendarData | undefined {
  const start = Date.parse(from)
  const end = Date.parse(to)
  const firstDay = wallDate(from, tz)
  const lastDay = wallDate(new Date(end - 1).toISOString(), tz)
  for (const [key, data] of queryClient.getQueriesData<CalendarData>({ queryKey: queryKeys.calendarAll })) {
    const [, qFrom, qTo] = key as string[]
    if (!data || !qFrom || !qTo || Date.parse(qFrom) > start || Date.parse(qTo) < end) continue
    if (qFrom === from && qTo === to) continue
    return {
      events: data.events.filter((e) => Date.parse(e.start) < end && Date.parse(e.end) > start),
      days_off: data.days_off.filter((d) => d.date_from <= lastDay && d.date_to >= firstDay),
    }
  }
  return undefined
}

/** События, пересекающие [from, to) (ISO-моменты с Z). */
export function useCalendar(from: string | undefined, to: string | undefined) {
  const queryClient = useQueryClient()
  const tz = useTimeZone()
  return useQuery({
    ...calendarQueryOptions(from ?? '', to ?? ''),
    enabled: !!from && !!to,
    placeholderData: (prev) => (from && to && cachedSubrange(queryClient, from, to, tz)) || prev,
  })
}

function useInvalidateCalendar() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
}

export function useCreateEvent() {
  const invalidate = useInvalidateCalendar()
  return useMutation({
    mutationFn: async (body: EventCreate) => {
      const { data, error } = await api.POST('/api/v1/events', { body })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** Как на бэкенде (services/events._is_manual_edit): «сделано», pin и заметка не отвязывают вхождение от серии. */
function isManualEdit(body: EventUpdate): boolean {
  if (body.status === 'cancelled') return true
  return Object.keys(body).some((k) => !['status', 'is_pinned', 'note'].includes(k))
}

/** Правка события — optimistic: календарь и «Сегодня» меняются сразу. */
export function useUpdateEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: EventUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/events/{event_id}', {
        params: { path: { event_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.calendarAll })
      const snapshot = queryClient.getQueriesData<CalendarData>({ queryKey: queryKeys.calendarAll })
      queryClient.setQueriesData<CalendarData>({ queryKey: queryKeys.calendarAll }, (old) =>
        old && {
          ...old,
          events: old.events.map((e) =>
            e.id === id
              ? ({ ...e, ...body, detached: e.detached || (!!e.template_id && isManualEdit(body)) } as CalendarEvent)
              : e,
          ),
        },
      )
      return { snapshot }
    },
    onError: (error, _vars, context) => {
      for (const [key, data] of context?.snapshot ?? []) queryClient.setQueryData(key, data)
      toast.error(errorMessage(error))
    },
    onSettled: (_data, _error, { body }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
      // «Сделано» на блоке закрывает и источник: подзадачу, дело из ящика, день подготовки
      if (body.status) {
        for (const queryKey of [queryKeys.tasks, queryKeys.backlogAll, queryKeys.examsAll, queryKeys.review]) {
          queryClient.invalidateQueries({ queryKey })
        }
      }
    },
  })
}

export function useDeleteEvent() {
  const invalidate = useInvalidateCalendar()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/events/{event_id}', {
        params: { path: { event_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useResetEvent() {
  const invalidate = useInvalidateCalendar()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.POST('/api/v1/events/{event_id}/reset', {
        params: { path: { event_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      invalidate()
      toast.success('Вернули как в расписании')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- личные повторы ----------

export function useRecurringEvents() {
  return useQuery({
    queryKey: queryKeys.recurring,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/recurring-events')
      if (error) throw error
      return data
    },
  })
}

function useInvalidateRecurring() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.recurring })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
  }
}

export function useCreateRecurring() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async (body: RecurringEventCreate) => {
      const { data, error } = await api.POST('/api/v1/recurring-events', { body })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateRecurring() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: RecurringEventUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/recurring-events/{recurring_id}', {
        params: { path: { recurring_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteRecurring() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/recurring-events/{recurring_id}', {
        params: { path: { recurring_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}
