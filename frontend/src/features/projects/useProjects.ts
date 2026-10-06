import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { useInvalidateTasks } from '@/features/tasks/useTasks'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Project = components['schemas']['ProjectRead']
export type ProjectDetail = components['schemas']['ProjectDetail']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']
export type ProjectStatus = components['schemas']['ProjectStatus']
export type Milestone = components['schemas']['MilestoneRead']
export type MilestoneCreate = components['schemas']['MilestoneCreate']
export type MilestoneUpdate = components['schemas']['MilestoneUpdate']
export type WorkTaskCreate = components['schemas']['WorkTaskCreate']

export function useProjects(status: ProjectStatus[] = ['active']) {
  return useQuery({
    queryKey: [...queryKeys.projects, 'list', status],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/projects', { params: { query: { status } } })
      if (error) throw error
      return data
    },
  })
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.project(id ?? ''),
    enabled: !!id,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/projects/{project_id}', {
        params: { path: { project_id: id! } },
      })
      if (error) throw error
      return data
    },
  })
}

function useInvalidateProjects() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.projects })
}

export function useCreateProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (body: ProjectCreate) => {
      const { data, error } = await api.POST('/api/v1/projects', { body })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateProject() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ProjectUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/projects/{project_id}', {
        params: { path: { project_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      const key = queryKeys.project(id)
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<ProjectDetail>(key)
      if (prev) queryClient.setQueryData<ProjectDetail>(key, { ...prev, ...(body as Partial<ProjectDetail>) })
      return { prev }
    },
    onError: (error, { id }, context) => {
      if (context?.prev) queryClient.setQueryData(queryKeys.project(id), context.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useDeleteProject() {
  const invalidate = useInvalidateProjects()
  const invalidateTasks = useInvalidateTasks()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/projects/{project_id}', {
        params: { path: { project_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      invalidate()
      invalidateTasks()
      toast.success('Проект удалён')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useAddMilestone(projectId: string) {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (body: MilestoneCreate) => {
      const { data, error } = await api.POST('/api/v1/projects/{project_id}/milestones', {
        params: { path: { project_id: projectId } },
        body,
      })
      if (error) throw error
      return data
    },
    onSettled: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateMilestone(projectId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: MilestoneUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/milestones/{milestone_id}', {
        params: { path: { milestone_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      const key = queryKeys.project(projectId)
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<ProjectDetail>(key)
      if (prev) {
        queryClient.setQueryData<ProjectDetail>(key, {
          ...prev,
          milestones: prev.milestones.map((m) => (m.id === id ? ({ ...m, ...body } as Milestone) : m)),
        })
      }
      return { prev }
    },
    onError: (error, _vars, context) => {
      if (context?.prev) queryClient.setQueryData(queryKeys.project(projectId), context.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useDeleteMilestone() {
  const invalidate = useInvalidateProjects()
  const invalidateTasks = useInvalidateTasks()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/milestones/{milestone_id}', {
        params: { path: { milestone_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      invalidate()
      invalidateTasks()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useCreateWorkTask() {
  const invalidate = useInvalidateProjects()
  const invalidateTasks = useInvalidateTasks()
  return useMutation({
    mutationFn: async (body: WorkTaskCreate) => {
      const { data, error } = await api.POST('/api/v1/tasks/work', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      invalidate()
      invalidateTasks()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
