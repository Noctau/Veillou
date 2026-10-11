import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'
import { AREAS_UI } from '@/lib/terms'

export type Area = components['schemas']['AreaRead']
export type AreaCreate = components['schemas']['AreaCreate']
export type AreaUpdate = components['schemas']['AreaUpdate']
export type AreaType = components['schemas']['AreaTypeRead']
export type AreaTypeCreate = components['schemas']['AreaTypeCreate']
export type AreaTypeUpdate = components['schemas']['AreaTypeUpdate']
export type AreaSection = components['schemas']['AreaSection']
export type FieldDef = components['schemas']['FieldDefRead']
export type FieldDefIn = components['schemas']['FieldDefIn']
export type FieldType = components['schemas']['FieldType']
export type FieldValues = Area['fields']

const STALE = 5 * 60_000

/** Все сферы пользователя (и архивные — с `archived_at`); фильтры — на клиенте. */
export function useAreas() {
  return useQuery({
    queryKey: queryKeys.areas,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/areas')
      if (error) throw error
      return data
    },
  })
}

/** Живые сферы — для выбора в задачах, заметках и ＋. Текущая остаётся, даже если в архиве. */
export function selectableAreas(areas: Area[] | undefined, current?: string | null): Area[] {
  return (areas ?? []).filter((a) => !a.archived_at || a.id === current)
}

export function useAreaTypes() {
  return useQuery({
    queryKey: queryKeys.areaTypes,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/area-types')
      if (error) throw error
      return data
    },
  })
}

function useInvalidateAreas() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all(
      // Название и цвет сферы видны в занятиях и календаре
      [queryKeys.areas, queryKeys.classRulesAll, queryKeys.calendarAll].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    )
}

export function useCreateArea() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: AreaCreate) => {
      const { data, error } = await api.POST('/api/v1/areas', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<Area[]>(queryKeys.areas, (old) =>
        old ? [...old, data].sort((a, b) => a.name.localeCompare(b.name, 'ru')) : old,
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.areas })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateArea() {
  const invalidate = useInvalidateAreas()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: AreaUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/areas/{area_id}', {
        params: { path: { area_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteArea() {
  const invalidate = useInvalidateAreas()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/areas/{area_id}', {
        params: { path: { area_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      invalidate()
      toast.success(AREAS_UI.deleted)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

function useInvalidateTypes() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.areaTypes })
}

export function useCreateAreaType() {
  const invalidate = useInvalidateTypes()
  return useMutation({
    mutationFn: async (body: AreaTypeCreate) => {
      const { data, error } = await api.POST('/api/v1/area-types', { body })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateAreaType() {
  const invalidate = useInvalidateTypes()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: AreaTypeUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/area-types/{area_type_id}', {
        params: { path: { area_type_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteAreaType() {
  const invalidate = useInvalidateTypes()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/area-types/{area_type_id}', {
        params: { path: { area_type_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
}
