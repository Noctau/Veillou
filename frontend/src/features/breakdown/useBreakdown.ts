import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { useInvalidateTasks } from '@/features/tasks/useTasks'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type BreakdownStep = components['schemas']['BreakdownStep']
export type BreakdownApply = components['schemas']['BreakdownApply']
export type BreakdownRequest = components['schemas']['BreakdownRequest']
export type Template = components['schemas']['TemplateRead']
export type TemplateCreate = components['schemas']['TemplateCreate']

/** «Разбить на шаги» / «Перегенерировать»: возвращает id джобы, черновик — через useJob. */
export function useStartBreakdown(taskId: string) {
  return useMutation({
    mutationFn: async (body: BreakdownRequest) => {
      const { data, error } = await api.POST('/api/v1/tasks/{task_id}/breakdown', {
        params: { path: { task_id: taskId } },
        body,
      })
      if (error) throw error
      return data.job_id
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** Неприменённая разбивка задания: ждёт ИИ, считается или готова (пользователь мог уйти со страницы). */
export function useLatestBreakdown(taskId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.latestBreakdown(taskId),
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/tasks/{task_id}/breakdown/latest', {
        params: { path: { task_id: taskId } },
      })
      if (error) throw error
      return data ?? null
    },
    // Пока не готово — обновляем, чтобы баннер сменился на «готово»
    refetchInterval: (query) => (query.state.data && query.state.data.status !== 'done' ? 15_000 : false),
  })
}

/** «Распознать фото задания»: текст, срок и предмет попадут в само задание. */
export function useRecognizePhoto(taskId: string) {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/tasks/{task_id}/recognize', {
        params: { path: { task_id: taskId } },
      })
      if (error) throw error
      return data.job_id
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** «Запланировать»: шаги сохраняются, превью плана сразу попадает в шторку. */
export function useApplyBreakdown(taskId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (body: BreakdownApply) => {
      const { data, error } = await api.POST('/api/v1/tasks/{task_id}/breakdown/apply', {
        params: { path: { task_id: taskId } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.task(taskId), data.task)
      queryClient.setQueryData(queryKeys.latestBreakdown(taskId), null)
      if (data.plan) queryClient.setQueryData(queryKeys.plan, data.plan)
      invalidate()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- шаблоны ----------

export function useTemplates() {
  return useQuery({
    queryKey: queryKeys.breakdownTemplates,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/breakdown-templates')
      if (error) throw error
      return data
    },
  })
}

export function useCreateTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TemplateCreate) => {
      const { data, error } = await api.POST('/api/v1/breakdown-templates', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.breakdownTemplates })
      toast.success(`Шаблон «${data.name}» сохранён`)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/breakdown-templates/{template_id}', {
        params: { path: { template_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.breakdownTemplates }),
    onError: (error) => toast.error(errorMessage(error)),
  })
}
