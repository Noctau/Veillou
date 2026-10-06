import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Semester = components['schemas']['SemesterRead']
export type SemesterCreate = components['schemas']['SemesterCreate']
export type SemesterUpdate = components['schemas']['SemesterUpdate']
export type BellSchedule = components['schemas']['BellScheduleRead']
export type BellScheduleIn = components['schemas']['BellScheduleIn']
export type BellSlot = components['schemas']['BellSlot-Output']
export type DayOff = components['schemas']['DayOffRead']
export type DayOffCreate = components['schemas']['DayOffCreate']
export type ClassRule = components['schemas']['ClassRuleRead']
export type ClassRuleCreate = components['schemas']['ClassRuleCreate']
export type ClassRuleUpdate = components['schemas']['ClassRuleUpdate']
export type Parity = components['schemas']['Parity']
export type RuleParity = components['schemas']['RuleParity']
export type ClassType = components['schemas']['ClassType']

/** Изменения шаблонов пересобирают вхождения -> календарь устарел. */
function useInvalidateSchedule() {
  const queryClient = useQueryClient()
  return (...keys: (readonly unknown[])[]) => {
    for (const key of keys) queryClient.invalidateQueries({ queryKey: key })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
  }
}

// ---------- семестры ----------

export function useSemesters() {
  return useQuery({
    queryKey: queryKeys.semesters,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/semesters')
      if (error) throw error
      return data
    },
  })
}

/** Текущий семестр: идущий сейчас, иначе ближайший будущий, иначе последний. */
export function pickCurrentSemester(semesters: Semester[], today: string): Semester | undefined {
  const end = (s: Semester) => s.session_end ?? s.classes_end
  return (
    semesters.find((s) => s.start_date <= today && today <= end(s)) ??
    [...semesters].filter((s) => s.start_date > today).sort((a, b) => a.start_date.localeCompare(b.start_date))[0] ??
    semesters[0]
  )
}

export function useCreateSemester() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ semester, bells }: { semester: SemesterCreate; bells: BellScheduleIn[] }) => {
      const { data, error } = await api.POST('/api/v1/semesters', { body: semester })
      if (error) throw error
      const res = await api.PUT('/api/v1/semesters/{semester_id}/bells', {
        params: { path: { semester_id: data.id } },
        body: { schedules: bells },
      })
      if (res.error) throw res.error
      return data
    },
    onSuccess: () => {
      invalidate(queryKeys.semesters)
      toast.success('Семестр создан')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateSemester() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: SemesterUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/semesters/{semester_id}', {
        params: { path: { semester_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      invalidate(queryKeys.semesters)
      toast.success('Сохранено')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- звонки ----------

export function useBells(semesterId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.bells(semesterId ?? ''),
    enabled: !!semesterId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/semesters/{semester_id}/bells', {
        params: { path: { semester_id: semesterId! } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useReplaceBells(semesterId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (schedules: BellScheduleIn[]) => {
      const { data, error } = await api.PUT('/api/v1/semesters/{semester_id}/bells', {
        params: { path: { semester_id: semesterId } },
        body: { schedules },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.bells(semesterId), data)
      invalidate()
      toast.success('Звонки сохранены')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- выходные ----------

export function useDaysOff() {
  return useQuery({
    queryKey: queryKeys.daysOff,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/days-off')
      if (error) throw error
      return data
    },
  })
}

export function useCreateDayOff() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: DayOffCreate) => {
      const { data, error } = await api.POST('/api/v1/days-off', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.daysOff),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteDayOff() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/days-off/{day_off_id}', {
        params: { path: { day_off_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.daysOff),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

// ---------- правила пар ----------

export function useClassRules(semesterId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.classRules(semesterId ?? ''),
    enabled: !!semesterId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/class-rules', {
        params: { query: { semester_id: semesterId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCreateClassRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (body: ClassRuleCreate) => {
      const { data, error } = await api.POST('/api/v1/class-rules', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.classRulesAll),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateClassRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ClassRuleUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/class-rules/{rule_id}', {
        params: { path: { rule_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(queryKeys.classRulesAll),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteClassRule() {
  const invalidate = useInvalidateSchedule()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/class-rules/{rule_id}', {
        params: { path: { rule_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(queryKeys.classRulesAll),
    onError: (error) => toast.error(errorMessage(error)),
  })
}
