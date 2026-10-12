import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'

export type Bundle = components['schemas']['ConfigBundle-Output']
export type BundleInput = components['schemas']['ConfigBundle-Input']
export type ImportResult = components['schemas']['BundleImportResult']
export type SetupDraft = components['schemas']['SetupDraft']
export type SetupRequest = components['schemas']['SetupRequest']

/** «Настроить по описанию»: ставит джобу ИИ, возвращает её id. */
export function useStartSetup() {
  return useMutation({
    mutationFn: async (body: SetupRequest) => {
      const { data, error } = await api.POST('/api/v1/config/ai-setup', { body })
      if (error) throw error
      return data.job_id
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** Импорт сборки: `dryRun` — только отчёт; иначе всё сохранённое перечитывается. */
export function useImportBundle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ bundle, dryRun }: { bundle: BundleInput; dryRun: boolean }) => {
      const { data, error } = await api.POST('/api/v1/config/import', {
        params: { query: { dry_run: dryRun } },
        body: bundle,
      })
      if (error) throw error
      return data
    },
    onSuccess: (result) => {
      if (!result.dry_run) queryClient.invalidateQueries()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export async function exportBundle(): Promise<Bundle> {
  const { data, error } = await api.GET('/api/v1/config/export')
  if (error) throw error
  return data
}
