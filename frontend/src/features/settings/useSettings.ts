import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type UserSettings = components['schemas']['UserSettings']
export type UserSettingsPatch = components['schemas']['UserSettingsPatch']

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/me/settings')
      if (error) throw error
      return data
    },
  })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: UserSettingsPatch) => {
      const { data, error } = await api.PATCH('/api/v1/me/settings', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data)
      toast.success('Сохранено')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
