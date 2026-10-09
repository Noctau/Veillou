import { useMutation, useQueryClient } from '@tanstack/react-query'

import type { components } from '@/api/schema'
import { unsubscribeThisDevice } from '@/features/notifications/usePush'
import { api } from '@/lib/api'
import { clearOfflineData } from '@/lib/persist'
import { queryKeys } from '@/lib/queryKeys'

type LoginRequest = components['schemas']['LoginRequest']

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: LoginRequest) => {
      const { data, error } = await api.POST('/api/v1/auth/login', { body })
      if (error) throw error
      return data
    },
    onSuccess: (me) => queryClient.setQueryData(queryKeys.me, me),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      // Пока сессия жива: иначе устройство и после выхода получало бы напоминания
      // (с кнопками, которые работают без входа). Сбой отписки выход не блокирует.
      await unsubscribeThisDevice({ quick: true }).catch(() => undefined)
      await api.POST('/api/v1/auth/logout')
    },
    onSettled: async () => {
      await clearOfflineData()
      queryClient.setQueryData(queryKeys.me, null)
    },
  })
}
