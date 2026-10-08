import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorCode, errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type PlanState = components['schemas']['PlanState']
export type PlanRevision = components['schemas']['PlanRevisionRead']
export type PlanChange = components['schemas']['PlanChange']
export type PlanRisk = components['schemas']['PlanRisk']
export type RiskReason = components['schemas']['RiskReason']
export type PlanReason = components['schemas']['PlanReason']
export type Calibration = components['schemas']['CalibrationRead']

/** Превью плана и что можно откатить. Превью после правок считает воркер — опрашиваем. */
export function usePlanState() {
  return useQuery({
    queryKey: queryKeys.plan,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/plan')
      if (error) throw error
      return data
    },
    // Превью могло появиться в любой момент (воркер) — при открытии всегда свежее
    staleTime: 0,
    refetchInterval: 30_000,
  })
}

/** После применения/отката меняются блоки: календарь, задания, «Сегодня», дни подготовки. */
function useInvalidatePlanned() {
  const queryClient = useQueryClient()
  return () => {
    for (const queryKey of [queryKeys.calendarAll, queryKeys.tasks, queryKeys.examsAll, queryKeys.review]) {
      queryClient.invalidateQueries({ queryKey })
    }
  }
}

/** «Перепланировать»: считает превью сразу (до 2 с). `quiet` — без тоста «менять нечего». */
export function usePreviewPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ reason = 'manual' }: { reason?: PlanReason; quiet?: boolean } = {}) => {
      const { data, error } = await api.POST('/api/v1/plan/preview', { params: { query: { reason } } })
      if (error) throw error
      return data
    },
    onSuccess: (data, vars) => {
      queryClient.setQueryData(queryKeys.plan, data)
      if (!data.proposal && !vars?.quiet) toast.success('План актуален — менять нечего')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUndoPlan() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidatePlanned()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/plan/undo')
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      const kept = data.skipped ? ` (${data.skipped} изменённых вручную оставили)` : ''
      toast.success(`Вернули план как было${kept}`)
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: queryKeys.plan })
    },
  })
}

export function useApplyPlan() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidatePlanned()
  const undo = useUndoPlan()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.POST('/api/v1/plan/revisions/{revision_id}/apply', {
        params: { path: { revision_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.plan, data)
      invalidate()
      toast.success('План обновлён', { action: { label: 'Отменить', onClick: () => undo.mutate() } })
    },
    onError: (error) => {
      // План успел измениться: новое превью уже посчитано — шторка покажет его
      if (errorCode(error) === 'plan_stale') toast.info(errorMessage(error))
      else toast.error(errorMessage(error))
      queryClient.invalidateQueries({ queryKey: queryKeys.plan })
    },
  })
}

/** «Отменить» в шторке: превью скрывается сразу (optimistic), план не меняется. */
export function useDismissPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.POST('/api/v1/plan/revisions/{revision_id}/dismiss', {
        params: { path: { revision_id: id } },
      })
      if (error) throw error
      return data
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.plan })
      const prev = queryClient.getQueryData<PlanState>(queryKeys.plan)
      if (prev) queryClient.setQueryData<PlanState>(queryKeys.plan, { ...prev, proposal: null })
      return { prev }
    },
    onError: (error, _id, context) => {
      if (context?.prev) queryClient.setQueryData(queryKeys.plan, context.prev)
      toast.error(errorMessage(error))
    },
    onSuccess: (data) => queryClient.setQueryData(queryKeys.plan, data),
  })
}

/** Разовый лимит учёбы на день (вариант «больше учёбы в этот день»). */
export function usePutDayLimit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ day, minutes }: { day: string; minutes: number }) => {
      const { data, error } = await api.PUT('/api/v1/plan/day-limits/{day}', {
        params: { path: { day } },
        body: { minutes },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.dayLimits }),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- калибровка ----------

export function useCalibration() {
  return useQuery({
    queryKey: queryKeys.calibration,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/calibration')
      if (error) throw error
      return data
    },
  })
}

export function useResetCalibration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/calibration/reset')
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.calibration, data)
      toast.success('Калибровка сброшена')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
