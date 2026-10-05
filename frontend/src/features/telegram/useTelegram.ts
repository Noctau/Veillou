import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

/** Статус привязки. `waiting` — пока показан код: опрашиваем, не привязалась ли. */
export function useTelegramStatus({ waiting = false } = {}) {
  return useQuery({
    queryKey: queryKeys.telegram,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/me/telegram')
      if (error) throw error
      return data
    },
    refetchInterval: (query) => (waiting && !query.state.data?.linked ? 3_000 : false),
  })
}

export function useCreateLinkCode() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/me/telegram/link-code')
      if (error) throw error
      return data
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUnlinkTelegram() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE('/api/v1/me/telegram')
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.telegram })
      toast.success('Telegram отвязан')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
