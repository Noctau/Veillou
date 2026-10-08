import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type EveningReview = components['schemas']['EveningReview']
export type WeeklyReview = components['schemas']['WeeklyReview']
export type FreeSuggestion = components['schemas']['FreeSuggestion']

/** Вечерний разбор: начатые и прошедшие блоки дня без отметки. */
export function useEveningReview() {
  return useQuery({
    queryKey: queryKeys.eveningReview('today'),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/review/evening')
      if (error) throw error
      return data
    },
    staleTime: 0,
  })
}

/** «Перенести всё» (или выбранное): блоки → «не сделано», превью плана — в шторке. */
export function useReschedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (eventIds?: string[]) => {
      const { data, error } = await api.POST('/api/v1/review/evening/reschedule', {
        body: { event_ids: eventIds ?? null },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.plan, data.plan)
      if (!data.moved) toast.info('Переносить нечего')
      else if (data.plan.proposal) toast.success('Проверьте превью плана внизу и примените')
      else toast.success('Отмечено «не сделано» — план уже это учитывает')
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.review })
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    },
  })
}

export function useWeeklyReview() {
  return useQuery({
    queryKey: queryKeys.weeklyReview,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/review/week')
      if (error) throw error
      return data
    },
    staleTime: 0,
  })
}

/** Дела из ящика на неделю (список целиком) → превью плана. */
export function useConfirmWeek() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (itemIds: string[]) => {
      const { data, error } = await api.POST('/api/v1/review/week/confirm', { body: { item_ids: itemIds } })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.plan, data.plan)
      toast.success(data.plan.proposal ? 'Проверьте превью плана внизу и примените' : 'Сохранено')
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.review })
      queryClient.invalidateQueries({ queryKey: queryKeys.backlogAll })
    },
  })
}

/** «У меня есть N минут». */
export function useFree(minutes: number | null) {
  return useQuery({
    queryKey: queryKeys.free(minutes ?? 0),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/free', { params: { query: { minutes: minutes ?? 0 } } })
      if (error) throw error
      return data
    },
    enabled: minutes != null,
    staleTime: 0,
  })
}

/** «Начать»: блок на сейчас, закреплённый. */
export function useStartFree() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (item: FreeSuggestion) => {
      const { data, error } = await api.POST('/api/v1/free/start', { body: { kind: item.kind, id: item.id } })
      if (error) throw error
      return data
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
      queryClient.invalidateQueries({ queryKey: ['free'] })
    },
  })
}
