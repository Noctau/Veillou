import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Subject = components['schemas']['SubjectRead']
export type SubjectCreate = components['schemas']['SubjectCreate']
export type SubjectUpdate = components['schemas']['SubjectUpdate']
export type ControlForm = components['schemas']['ControlForm']

export const CONTROL_FORM_LABEL: Record<ControlForm, string> = {
  exam: 'Экзамен',
  credit: 'Зачёт',
  graded_credit: 'Дифзачёт',
  coursework: 'Курсовая',
  none: 'Без контроля',
}

/** Все предметы пользователя; фильтр по семестру — на клиенте. */
export function useSubjects() {
  return useQuery({
    queryKey: queryKeys.subjects,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/subjects')
      if (error) throw error
      return data
    },
  })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.subjects })
    // Название/цвет предмета видны в парах и календаре
    queryClient.invalidateQueries({ queryKey: queryKeys.classRulesAll })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
  }
}

export function useCreateSubject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: SubjectCreate) => {
      const { data, error } = await api.POST('/api/v1/subjects', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<Subject[]>(queryKeys.subjects, (old) =>
        old ? [...old, data].sort((a, b) => a.name.localeCompare(b.name, 'ru')) : old,
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.subjects })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateSubject() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: SubjectUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/subjects/{subject_id}', {
        params: { path: { subject_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteSubject() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/subjects/{subject_id}', {
        params: { path: { subject_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      invalidate()
      toast.success('Предмет удалён')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
