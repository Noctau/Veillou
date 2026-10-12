import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'
import { SCHEDULE_UI as T } from '@/lib/terms'

type Schemas = components['schemas']

export type EventType = Schemas['EventTypeRead']
export type EventTypeCreate = Schemas['EventTypeCreate']
export type EventTypeUpdate = Schemas['EventTypeUpdate']
export type Period = Schemas['PeriodRead']
export type PeriodCreate = Schemas['PeriodCreate']
export type PeriodUpdate = Schemas['PeriodUpdate']
export type Pause = Schemas['Pause']
export type SlotGridRow = Schemas['SlotGridRead']
export type SlotGridPut = Schemas['SlotGridPut']
export type SlotGridDay = Schemas['SlotGridDay-Input']
export type Slot = Schemas['SlotRead']
export type DayOff = Schemas['DayOffRead']
export type DayOffCreate = Schemas['DayOffCreate']
export type ScheduleRule = Schemas['ScheduleRuleRead']
export type ScheduleRuleCreate = Schemas['ScheduleRuleCreate']
export type ScheduleRuleUpdate = Schemas['ScheduleRuleUpdate']
export type Pattern = ScheduleRule['pattern']
export type Channel = Schemas['Channel']

const STALE = 5 * 60_000

/** Изменения расписания пересобирают вхождения -> календарь устарел. */
function useInvalidateSchedule() {
  const queryClient = useQueryClient()
  return (...keys: (readonly unknown[])[]) => {
    for (const key of keys) queryClient.invalidateQueries({ queryKey: key })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
  }
}

function onError(error: unknown) {
  toast.error(errorMessage(error))
}

// ---------- типы занятости ----------

export function useEventTypes() {
  return useQuery({
    queryKey: queryKeys.eventTypes,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/event-types')
      if (error) throw error
      return data
    },
  })
}

export function useCreateEventType() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: EventTypeCreate) => {
      const { data, error } = await api.POST('/api/v1/event-types', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.eventTypes),
    onError,
  })
}

export function useUpdateEventType() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: EventTypeUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/event-types/{type_id}', {
        params: { path: { type_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.eventTypes, queryKeys.budgets),
    onError,
  })
}

export function useDeleteEventType() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/event-types/{type_id}', {
        params: { path: { type_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.eventTypes, queryKeys.scheduleRulesAll, queryKeys.budgets, queryKeys.backlogAll),
    onError,
  })
}

// ---------- периоды ----------

export function usePeriods() {
  return useQuery({
    queryKey: queryKeys.periods,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/periods')
      if (error) throw error
      return data
    },
  })
}

/** Текущий период: идущий сейчас, иначе ближайший будущий, иначе последний. */
export function pickCurrentPeriod(periods: Period[], today: string): Period | undefined {
  return (
    periods.find((p) => p.start_date <= today && today <= p.end_date) ??
    [...periods].filter((p) => p.start_date > today).sort((a, b) => a.start_date.localeCompare(b.start_date))[0] ??
    periods[0]
  )
}

export function useCreatePeriod() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ period, slots }: { period: PeriodCreate; slots?: SlotGridDay[] }) => {
      const { data, error } = await api.POST('/api/v1/periods', { body: period })
      if (error) throw error
      if (slots) {
        const res = await api.PUT('/api/v1/slot-grids', {
          body: { period_id: data.id, name: T.defaultGrid, schedules: slots },
        })
        if (res.error) throw res.error
      }
      return data
    },
    onSuccess: () => {
      invalidate(queryKeys.periods, queryKeys.slotGrids)
      toast.success(T.periodCreated)
    },
    onError,
  })
}

export function useUpdatePeriod() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: PeriodUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/periods/{period_id}', {
        params: { path: { period_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      invalidate(queryKeys.periods)
      toast.success(T.saved)
    },
    onError,
  })
}

export function useDeletePeriod() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/periods/{period_id}', {
        params: { path: { period_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () =>
      invalidate(queryKeys.periods, queryKeys.slotGrids, queryKeys.scheduleRulesAll, queryKeys.daysOff, queryKeys.areas),
    onError,
  })
}

// ---------- сетки слотов ----------

export function useSlotGrids() {
  return useQuery({
    queryKey: queryKeys.slotGrids,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/slot-grids')
      if (error) throw error
      return data
    },
  })
}

/** Сетка — строки с одним (period_id, name); общая строка (weekday = null) — её id. */
export type SlotGrid = { id: string; period_id: string | null; name: string; rows: SlotGridRow[] }

export function groupGrids(rows: SlotGridRow[]): SlotGrid[] {
  const heads = rows.filter((r) => r.weekday === null)
  return heads.map((h) => ({
    id: h.id,
    period_id: h.period_id,
    name: h.name,
    rows: rows.filter((r) => r.period_id === h.period_id && r.name === h.name),
  }))
}

/** Слоты сетки на день недели: переопределение дня или общие. */
export function slotsFor(grid: SlotGrid | undefined, weekday: number): Slot[] {
  if (!grid) return []
  return (grid.rows.find((r) => r.weekday === weekday) ?? grid.rows.find((r) => r.weekday === null))?.slots ?? []
}

export function usePutSlotGrid() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: SlotGridPut) => {
      const { data, error } = await api.PUT('/api/v1/slot-grids', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      invalidate(queryKeys.slotGrids)
      toast.success(T.gridSaved)
    },
    onError,
  })
}

export function useDeleteSlotGrid() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/slot-grids/{grid_id}', {
        params: { path: { grid_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.slotGrids),
    onError,
  })
}

// ---------- исключения ----------

export function useDaysOff() {
  return useQuery({
    queryKey: queryKeys.daysOff,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/days-off')
      if (error) throw error
      return data
    },
  })
}

export function useCreateDayOff() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: DayOffCreate) => {
      const { data, error } = await api.POST('/api/v1/days-off', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.daysOff),
    onError,
  })
}

export function useDeleteDayOff() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/days-off/{day_off_id}', {
        params: { path: { day_off_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.daysOff),
    onError,
  })
}

// ---------- правила расписания ----------

export type RuleFilter = { period_id?: string; area_id?: string; event_type_id?: string }

export function useScheduleRules(filter: RuleFilter = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.scheduleRules(filter),
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/schedule-rules', { params: { query: filter } })
      if (error) throw error
      return data
    },
  })
}

export function useCreateScheduleRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: ScheduleRuleCreate) => {
      const { data, error } = await api.POST('/api/v1/schedule-rules', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.scheduleRulesAll),
    onError,
  })
}

export function useUpdateScheduleRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ScheduleRuleUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/schedule-rules/{rule_id}', {
        params: { path: { rule_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.scheduleRulesAll),
    onError,
  })
}

export function useDeleteScheduleRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/schedule-rules/{rule_id}', {
        params: { path: { rule_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.scheduleRulesAll),
    onError,
  })
}

/** Тело создания из прочитанного правила (копирование). */
export function ruleToCreate(rule: ScheduleRule): ScheduleRuleCreate {
  const { id: _, ...rest } = rule
  return rest
}
