import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

type Schemas = components['schemas']

export type DayProfile = Schemas['DayProfileRead']
export type DayProfileCreate = Schemas['DayProfileCreate']
export type DayProfileUpdate = Schemas['DayProfileUpdate']
export type DayProfileRule = Schemas['DayProfileRuleRead']
export type DayProfileRuleCreate = Schemas['DayProfileRuleCreate']
export type DayRuleKind = Schemas['DayRuleKind']
export type DayProfileDay = Schemas['DayProfileDay']

const STALE = 5 * 60_000

/** Режимы меняют план, напоминания и подписи дней в календаре. */
function useInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.dayProfilesAll })
    queryClient.invalidateQueries({ queryKey: queryKeys.plan })
  }
}

export function useDayProfiles() {
  return useQuery({
    queryKey: queryKeys.dayProfiles,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/day-profiles')
      if (error) throw error
      return data
    },
  })
}

export function useDayProfileRules() {
  return useQuery({
    queryKey: queryKeys.dayProfileRules,
    staleTime: STALE,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/day-profile-rules')
      if (error) throw error
      return data
    },
  })
}

/** Режим каждой даты отрезка (включительно, "YYYY-MM-DD"). */
export function useDayProfileDays(start: string, end: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.dayProfileDays(start, end),
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/day-profiles/days', {
        params: { query: { start, end } },
      })
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

export function useCreateDayProfile() {
  return useMutate(async (body: DayProfileCreate) => {
    const { data, error } = await api.POST('/api/v1/day-profiles', { body })
    if (error) throw error
    return data
  })
}

export function useUpdateDayProfile() {
  return useMutate(async ({ id, body }: { id: string; body: DayProfileUpdate }) => {
    const { data, error } = await api.PATCH('/api/v1/day-profiles/{profile_id}', {
      params: { path: { profile_id: id } },
      body,
    })
    if (error) throw error
    return data
  })
}

export function useDeleteDayProfile() {
  return useMutate(async (id: string) => {
    const { error } = await api.DELETE('/api/v1/day-profiles/{profile_id}', {
      params: { path: { profile_id: id } },
    })
    if (error) throw error
  })
}

export function useCreateDayRule() {
  return useMutate(async (body: DayProfileRuleCreate) => {
    const { data, error } = await api.POST('/api/v1/day-profile-rules', { body })
    if (error) throw error
    return data
  })
}

export function useDeleteDayRule() {
  return useMutate(async (id: string) => {
    const { error } = await api.DELETE('/api/v1/day-profile-rules/{rule_id}', {
      params: { path: { rule_id: id } },
    })
    if (error) throw error
  })
}

export function useUpdateDayRule() {
  return useMutate(async ({ id, position }: { id: string; position: number }) => {
    const { data, error } = await api.PATCH('/api/v1/day-profile-rules/{rule_id}', {
      params: { path: { rule_id: id } },
      body: { position },
    })
    if (error) throw error
    return data
  })
}

/** Режим одной даты в одно касание; null — снова по правилам. */
export function useSetDayProfile() {
  return useMutate(async ({ day, profileId }: { day: string; profileId: string | null }) => {
    const { data, error } = await api.PUT('/api/v1/day-profiles/days/{day}', {
      params: { path: { day } },
      body: { profile_id: profileId },
    })
    if (error) throw error
    return data
  })
}
