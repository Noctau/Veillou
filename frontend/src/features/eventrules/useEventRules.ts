import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type EventRule = components['schemas']['EventRuleRead']
export type EventRuleCreate = components['schemas']['EventRuleCreate']
export type EventRuleUpdate = components['schemas']['EventRuleUpdate']
export type Owner = { event_type_id: string } | { schedule_rule_id: string }

/** Правила создают и убирают задачи сразу — списки задач и план устарели. */
function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.eventRulesAll })
    queryClient.invalidateQueries({ queryKey: queryKeys.tasks })
    queryClient.invalidateQueries({ queryKey: queryKeys.plan })
    queryClient.invalidateQueries({ queryKey: queryKeys.review })
  }
}

export function useEventRules(owner: Owner) {
  return useQuery({
    queryKey: queryKeys.eventRules(owner),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/event-rules', { params: { query: owner } })
      if (error) throw error
      return data
    },
  })
}

function useMutate<A, R>(fn: (arg: A) => Promise<R>) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: fn,
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useCreateEventRule() {
  return useMutate(async (body: EventRuleCreate) => {
    const { data, error } = await api.POST('/api/v1/event-rules', { body })
    if (error) throw error
    return data
  })
}

export function useUpdateEventRule() {
  return useMutate(async ({ id, body }: { id: string; body: EventRuleUpdate }) => {
    const { data, error } = await api.PATCH('/api/v1/event-rules/{rule_id}', {
      params: { path: { rule_id: id } },
      body,
    })
    if (error) throw error
    return data
  })
}

export function useDeleteEventRule() {
  return useMutate(async (id: string) => {
    const { error } = await api.DELETE('/api/v1/event-rules/{rule_id}', {
      params: { path: { rule_id: id } },
    })
    if (error) throw error
  })
}
