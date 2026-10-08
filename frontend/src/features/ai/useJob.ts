import { useQuery } from '@tanstack/react-query'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export type Job = components['schemas']['JobRead']
export type BreakdownDraft = components['schemas']['BreakdownDraft']
export type ParseDraft = components['schemas']['ParseDraft']
export type PhotoDraft = components['schemas']['PhotoDraft']

const POLL_MS = 1500
// ИИ недоступен — запрос в очереди: спрашиваем реже
const WAITING_POLL_MS = 10_000

function finished(job: Job | undefined) {
  return job?.status === 'done' || job?.status === 'failed'
}

/** Фоновая джоба ИИ: опрос раз в 1,5 с, пока не готова. Результат не кэшируется надолго. */
export function useJob(jobId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ''),
    enabled: !!jobId,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/jobs/{job_id}', {
        params: { path: { job_id: jobId! } },
      })
      if (error) throw error
      return data
    },
    refetchInterval: (query) => {
      const job = query.state.data
      if (finished(job)) return false
      return job?.waiting ? WAITING_POLL_MS : POLL_MS
    },
    // Готовый результат не меняется — не перезапрашиваем
    staleTime: (query) => (finished(query.state.data) ? Infinity : 0),
    gcTime: 10 * 60_000,
  })
}

/** Результат готовой джобы нужного типа (или undefined). */
export function jobResult<T extends NonNullable<Job['result']>['type']>(
  job: Job | undefined,
  type: T,
): Extract<NonNullable<Job['result']>, { type: T }> | undefined {
  const result = job?.status === 'done' ? job.result : null
  return result?.type === type ? (result as Extract<NonNullable<Job['result']>, { type: T }>) : undefined
}
