import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'
import { PREP_UI as T } from '@/lib/terms'

type Schemas = components['schemas']
export type PrepPlan = Schemas['PrepPlanRead']
export type PrepPlanDetail = Schemas['PrepPlanDetail']
export type PrepPlanCreate = Schemas['PrepPlanCreate']
export type PrepPlanUpdate = Schemas['PrepPlanUpdate']
export type PrepItem = Schemas['PrepItemRead']
export type PrepItemStatus = Schemas['PrepItemStatus']
export type PrepSession = Schemas['PrepSessionRead']
export type PrepStrategy = Schemas['PrepStrategy']
export type PlanFilter = { area_id?: string; event_id?: string }

export function usePrepPlans(filter: PlanFilter, enabled = true) {
  return useQuery({
    queryKey: queryKeys.prepPlans(filter),
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/prep-plans', { params: { query: filter } })
      if (error) throw error
      return data
    },
  })
}

export function usePrepPlan(id: string) {
  return useQuery({
    queryKey: queryKeys.prepPlan(id),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/prep-plans/{plan_id}', { params: { path: { plan_id: id } } })
      if (error) throw error
      return data
    },
  })
}

/** Ответ с деталями плана — в кэш; меняются и календарь, и (возможно) превью плана. */
function useOnDetail() {
  const queryClient = useQueryClient()
  return (data: PrepPlanDetail) => {
    queryClient.setQueryData(queryKeys.prepPlan(data.id), data)
    queryClient.invalidateQueries({ queryKey: queryKeys.prepList })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    queryClient.invalidateQueries({ queryKey: queryKeys.plan })
  }
}

export function useCreatePrepPlan() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async (body: PrepPlanCreate) => {
      const { data, error } = await api.POST('/api/v1/prep-plans', { body })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdatePrepPlan() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: PrepPlanUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/prep-plans/{plan_id}', {
        params: { path: { plan_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeletePrepPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, withEvent }: { id: string; withEvent: boolean }) => {
      const { error } = await api.DELETE('/api/v1/prep-plans/{plan_id}', {
        params: { path: { plan_id: id }, query: { with_event: withEvent } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.prepAll })
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useImportItems() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, text }: { id: string; text: string }) => {
      const { data, error } = await api.POST('/api/v1/prep-plans/{plan_id}/items/import', {
        params: { path: { plan_id: id } },
        body: { text },
      })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** Статус пункта — optimistic: отметка видна сразу, план пересоберётся на сервере. */
export function useUpdateItem(planId: string) {
  const queryClient = useQueryClient()
  const key = queryKeys.prepPlan(planId)
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: PrepItemStatus }) => {
      const { data, error } = await api.PATCH('/api/v1/prep-items/{item_id}', {
        params: { path: { item_id: id } },
        body: { status },
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<PrepPlanDetail>(key)
      if (prev) {
        queryClient.setQueryData<PrepPlanDetail>(key, {
          ...prev,
          items: prev.items.map((q) => (q.id === id ? { ...q, status } : q)),
        })
      }
      return { prev }
    },
    onError: (error, _vars, context) => {
      if (context?.prev) queryClient.setQueryData(key, context.prev)
      toast.error(errorMessage(error))
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: queryKeys.prepList })
    },
  })
}

/** «Построить план подготовки» → дни по пунктам + превью плана в шторке. */
export function usePrepEnable() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, enable }: { id: string; enable: boolean }) => {
      const params = { params: { path: { plan_id: id } } }
      const { data, error } = enable
        ? await api.POST('/api/v1/prep-plans/{plan_id}/enable', params)
        : await api.POST('/api/v1/prep-plans/{plan_id}/disable', params)
      if (error) throw error
      return data
    },
    onSuccess: (data, { enable }) => {
      onDetail(data)
      if (enable) toast.success(T.planReady)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
