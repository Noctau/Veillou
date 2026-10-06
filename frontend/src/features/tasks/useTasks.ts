import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components, operations } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Task = components['schemas']['TaskRead']
export type TaskDetail = components['schemas']['TaskDetail']
export type TaskCreate = components['schemas']['TaskCreate']
export type TaskUpdate = components['schemas']['TaskUpdate']
export type TaskType = components['schemas']['TaskType']
export type TaskStatus = components['schemas']['TaskStatus']
export type Priority = components['schemas']['Priority']
export type Subtask = components['schemas']['SubtaskRead']
export type SubtaskCreate = components['schemas']['SubtaskCreate']
export type SubtaskUpdate = components['schemas']['SubtaskUpdate']
export type Feel = components['schemas']['Feel']
export type TaskListParams = NonNullable<operations['list_tasks']['parameters']['query']>

export function useTasks(params: TaskListParams = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.taskList(params),
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/tasks', { params: { query: params } })
      if (error) throw error
      return data
    },
  })
}

export function useTask(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.task(id ?? ''),
    enabled: !!id,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/tasks/{task_id}', {
        params: { path: { task_id: id! } },
      })
      if (error) throw error
      return data
    },
  })
}

/** Задания, календарь (блоки подзадач) и проекты после любой правки. */
export function useInvalidateTasks() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.tasks })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    // Прогресс проекта считается по его заданиям
    queryClient.invalidateQueries({ queryKey: queryKeys.projects })
  }
}

export function useCreateTask() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (body: TaskCreate) => {
      const { data, error } = await api.POST('/api/v1/tasks', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.task(data.id), data)
      invalidate()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateTask() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: TaskUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/tasks/{task_id}', {
        params: { path: { task_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      const key = queryKeys.task(id)
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<TaskDetail>(key)
      if (prev) queryClient.setQueryData<TaskDetail>(key, { ...prev, ...(body as Partial<TaskDetail>) })
      return { prev }
    },
    onSuccess: (data) => queryClient.setQueryData(queryKeys.task(data.id), data),
    onError: (error, { id }, context) => {
      if (context?.prev) queryClient.setQueryData(queryKeys.task(id), context.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useDeleteTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/tasks/{task_id}', {
        params: { path: { task_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      invalidate()
      toast.success('Задание удалено')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
