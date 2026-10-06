import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Category = components['schemas']['CategoryRead']
export type CategoryCreate = components['schemas']['CategoryCreate']
export type CategoryUpdate = components['schemas']['CategoryUpdate']
export type CategoryIconName = components['schemas']['CategoryIcon']
export type ActionType = components['schemas']['ActionTypeRead']
export type ActionTypeKey = components['schemas']['ActionTypeKey']
export type ActionTypeUpdate = components['schemas']['ActionTypeUpdate']
// Вход и выход совпадают по форме (дни + "HH:MM")
export type TimeWindow = components['schemas']['TimeWindow-Output']

// Справочники меняются редко — не перезапрашиваем на каждый фокус
const STALE = 5 * 60_000

export function useCategories() {
  return useQuery({
    queryKey: queryKeys.categories,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/categories')
      if (error) throw error
      return data
    },
  })
}

export function useActionTypes() {
  return useQuery({
    queryKey: queryKeys.actionTypes,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/action-types')
      if (error) throw error
      return data
    },
  })
}

/** id → запись, для подписей и цветов в списках. */
export function byId<T extends { id: string }>(items: T[] | undefined): Map<string, T> {
  return new Map((items ?? []).map((i) => [i.id, i]))
}

function useInvalidate(key: readonly string[]) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: key })
}

export function useCreateCategory() {
  const invalidate = useInvalidate(queryKeys.categories)
  return useMutation({
    mutationFn: async (body: CategoryCreate) => {
      const { data, error } = await api.POST('/api/v1/categories', { body })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateCategory() {
  const invalidate = useInvalidate(queryKeys.categories)
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: CategoryUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/categories/{category_id}', {
        params: { path: { category_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteCategory() {
  const invalidate = useInvalidate(queryKeys.categories)
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/categories/{category_id}', {
        params: { path: { category_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateActionType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ActionTypeUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/action-types/{action_type_id}', {
        params: { path: { action_type_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<ActionType[]>(queryKeys.actionTypes, (old) =>
        old?.map((a) => (a.id === data.id ? data : a)),
      )
      toast.success('Сохранено')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useResetActionType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.POST('/api/v1/action-types/{action_type_id}/reset', {
        params: { path: { action_type_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<ActionType[]>(queryKeys.actionTypes, (old) =>
        old?.map((a) => (a.id === data.id ? data : a)),
      )
      toast.success('Вернули как было')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
