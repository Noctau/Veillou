import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type BacklogItem = components['schemas']['BacklogRead']
export type BacklogCreate = components['schemas']['BacklogCreate']
export type BacklogUpdate = components['schemas']['BacklogUpdate']
export type BacklogStatus = components['schemas']['BacklogStatus']
export type BacklogCondition = components['schemas']['BacklogCondition']

export function useBacklog(status: BacklogStatus = 'active') {
  return useQuery({
    queryKey: queryKeys.backlog(status),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/backlog', { params: { query: { status } } })
      if (error) throw error
      return data
    },
  })
}

/** Порядок активных как на сервере: с желаемым сроком первыми, дальше старые сверху. */
function sortActive(items: BacklogItem[]): BacklogItem[] {
  return [...items].sort((a, b) => {
    if (a.desired_by !== b.desired_by) {
      if (!a.desired_by) return 1
      if (!b.desired_by) return -1
      return a.desired_by.localeCompare(b.desired_by)
    }
    return a.created_at.localeCompare(b.created_at)
  })
}

/** Добавление — optimistic: дело появляется в списке сразу. */
export function useCreateBacklog() {
  const queryClient = useQueryClient()
  const key = queryKeys.backlog('active')
  return useMutation({
    mutationFn: async (body: BacklogCreate) => {
      const { data, error } = await api.POST('/api/v1/backlog', { body })
      if (error) throw error
      return data
    },
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<BacklogItem[]>(key)
      const draft: BacklogItem = {
        id: `tmp-${crypto.randomUUID()}`,
        title: body.title,
        note: body.note ?? '',
        category_id: body.category_id ?? null,
        action_type_id: body.action_type_id ?? null,
        estimate_min: body.estimate_min ?? null,
        desired_by: body.desired_by ?? null,
        conditions: body.conditions ?? [],
        time_window: null,
        status: 'active',
        planned_week: null,
        done_at: null,
        archived_at: null,
        created_at: new Date().toISOString(),
      }
      queryClient.setQueryData<BacklogItem[]>(key, (old) => sortActive([...(old ?? []), draft]))
      return { prev }
    },
    onError: (error, _body, context) => {
      queryClient.setQueryData(key, context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.backlogAll }),
  })
}

/** Правка — optimistic; смена статуса сразу убирает дело из текущего списка. */
export function useUpdateBacklog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: BacklogUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/backlog/{item_id}', {
        params: { path: { item_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.backlogAll })
      const snapshot = queryClient.getQueriesData<BacklogItem[]>({ queryKey: queryKeys.backlogAll })
      for (const [key, items] of snapshot) {
        if (!items) continue
        const listStatus = key[1] as BacklogStatus
        queryClient.setQueryData<BacklogItem[]>(
          key,
          items
            .map((i) => (i.id === id ? ({ ...i, ...body } as BacklogItem) : i))
            .filter((i) => i.status === listStatus),
        )
      }
      return { snapshot }
    },
    onError: (error, _vars, context) => {
      for (const [key, data] of context?.snapshot ?? []) queryClient.setQueryData(key, data)
      toast.error(errorMessage(error))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.backlogAll }),
  })
}

export function useDeleteBacklog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/backlog/{item_id}', {
        params: { path: { item_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.backlogAll }),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** «Взять на неделю» / «Снять с недели»: дело попадает в план (или уходит из него). */
export function useTakeForWeek() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, take }: { id: string; take: boolean }) => {
      const params = { params: { path: { item_id: id } } }
      const { data, error } = take
        ? await api.PUT('/api/v1/backlog/{item_id}/week', params)
        : await api.DELETE('/api/v1/backlog/{item_id}/week', params)
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      for (const [key, items] of queryClient.getQueriesData<BacklogItem[]>({ queryKey: queryKeys.backlogAll })) {
        if (items) queryClient.setQueryData(key, items.map((i) => (i.id === data.id ? data : i)))
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.review })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
