import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

/** Онбординг пройден или пропущен — больше не показываем. */
export function useFinishOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.PATCH('/api/v1/me/settings', { body: { onboarding_done: true } })
      if (error) throw error
      return data
    },
    onSuccess: (data) => queryClient.setQueryData(queryKeys.settings, data),
    onError: (error) => toast.error(errorMessage(error)),
  })
}
