import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

import { type Subtask, type SubtaskCreate, type SubtaskUpdate, type TaskDetail, useInvalidateTasks } from './useTasks'

/** Подзадачи живут в кэше задания: правки накладываем на него сразу (optimistic). */
function useTaskCache(taskId: string) {
  const queryClient = useQueryClient()
  const key = queryKeys.task(taskId)
  return {
    async patch(fn: (task: TaskDetail) => TaskDetail) {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<TaskDetail>(key)
      if (prev) queryClient.setQueryData<TaskDetail>(key, fn(prev))
      return { prev }
    },
    restore(prev: TaskDetail | undefined) {
      if (prev) queryClient.setQueryData(key, prev)
    },
  }
}

function withCounts(task: TaskDetail, subtasks: Subtask[]): TaskDetail {
  const done = subtasks.filter((s) => s.status === 'done').length
  const total = subtasks.length
  return {
    ...task,
    subtasks,
    subtasks_total: total,
    subtasks_done: done,
    progress: total ? done / total : task.status === 'done' ? 1 : 0,
  }
}

export function useAddSubtask(taskId: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (body: SubtaskCreate) => {
      const { data, error } = await api.POST('/api/v1/tasks/{task_id}/subtasks', {
        params: { path: { task_id: taskId } },
        body,
      })
      if (error) throw error
      return data
    },
    onSettled: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateSubtask(taskId: string) {
  const cache = useTaskCache(taskId)
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: SubtaskUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/subtasks/{subtask_id}', {
        params: { path: { subtask_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: ({ id, body }) =>
      cache.patch((task) =>
        withCounts(
          task,
          task.subtasks.map((s) => (s.id === id ? ({ ...s, ...body } as Subtask) : s)),
        ),
      ),
    onError: (error, _vars, context) => {
      cache.restore(context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useDeleteSubtask(taskId: string) {
  const cache = useTaskCache(taskId)
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/subtasks/{subtask_id}', {
        params: { path: { subtask_id: id } },
      })
      if (error) throw error
    },
    onMutate: (id) =>
      cache.patch((task) =>
        withCounts(
          task,
          task.subtasks
            .filter((s) => s.id !== id)
            .map((s) => ({ ...s, depends_on: s.depends_on.filter((d) => d !== id) })),
        ),
      ),
    onError: (error, _id, context) => {
      cache.restore(context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useReorderSubtasks(taskId: string) {
  const cache = useTaskCache(taskId)
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: async (ids: string[]) => {
      const { data, error } = await api.PUT('/api/v1/tasks/{task_id}/subtasks/order', {
        params: { path: { task_id: taskId } },
        body: { ids },
      })
      if (error) throw error
      return data
    },
    onMutate: (ids) =>
      cache.patch((task) => {
        const byId = new Map(task.subtasks.map((s) => [s.id, s]))
        return { ...task, subtasks: ids.map((id, position) => ({ ...byId.get(id)!, position })) }
      }),
    onError: (error, _ids, context) => {
      cache.restore(context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useScheduleSubtask(taskId: string) {
  const invalidate = useInvalidateTasks()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, start, end }: { id: string; start: string; end?: string }) => {
      const { data, error } = await api.POST('/api/v1/subtasks/{subtask_id}/schedule', {
        params: { path: { subtask_id: id } },
        body: { start, end: end ?? null },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<TaskDetail>(queryKeys.task(taskId), (old) =>
        old && { ...old, subtasks: old.subtasks.map((s) => (s.id === data.id ? data : s)) },
      )
      toast.success('Поставили в календарь')
    },
    onSettled: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUnscheduleSubtask(taskId: string) {
  const invalidate = useInvalidateTasks()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await api.DELETE('/api/v1/subtasks/{subtask_id}/schedule', {
        params: { path: { subtask_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) =>
      queryClient.setQueryData<TaskDetail>(queryKeys.task(taskId), (old) =>
        old && { ...old, subtasks: old.subtasks.map((s) => (s.id === data.id ? data : s)) },
      ),
    onSettled: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}
