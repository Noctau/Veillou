import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { useInvalidateTasks } from '@/features/tasks/useTasks'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Source = components['schemas']['SourceRead']
export type SourceCreate = components['schemas']['SourceCreate']
export type SourceUpdate = components['schemas']['SourceUpdate']
export type SourceKind = components['schemas']['SourceKind']
export type SourceStatus = components['schemas']['SourceStatus']
export type ReadingTaskCreate = components['schemas']['ReadingTaskCreate']

export const SOURCE_KIND_LABEL: Record<SourceKind, string> = {
  textbook: 'Учебник',
  article: 'Статья',
  website: 'Сайт',
  other: 'Другое',
}

export const SOURCE_STATUS_LABEL: Record<SourceStatus, string> = {
  to_read: 'Прочитать',
  reading: 'Читаю',
  done: 'Прочитано',
}

export function useSources(subjectId: string) {
  return useQuery({
    queryKey: queryKeys.sources(subjectId),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/sources', { params: { query: { subject_id: subjectId } } })
      if (error) throw error
      return data
    },
  })
}

export function useCreateSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: SourceCreate) => {
      const { data, error } = await api.POST('/api/v1/sources', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.sourcesAll }),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateSource(subjectId: string) {
  const queryClient = useQueryClient()
  const key = queryKeys.sources(subjectId)
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: SourceUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/sources/{source_id}', {
        params: { path: { source_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    // Статус «читаю / прочитано» — одним касанием, без ожидания сервера
    onMutate: async ({ id, body }) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<Source[]>(key)
      queryClient.setQueryData<Source[]>(key, (old) =>
        old?.map((s) => (s.id === id ? { ...s, ...(body as Partial<Source>) } : s)),
      )
      return { prev }
    },
    onError: (error, _vars, context) => {
      queryClient.setQueryData(key, context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.sourcesAll }),
  })
}

export function useDeleteSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/sources/{source_id}', { params: { path: { source_id: id } } })
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sourcesAll })
      toast.success('Источник удалён')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useCreateReadingTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ReadingTaskCreate }) => {
      const { data, error } = await api.POST('/api/v1/sources/{source_id}/reading-task', {
        params: { path: { source_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}
