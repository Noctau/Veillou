import { useMutation, useQueryClient } from '@tanstack/react-query'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
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
      await api.POST('/api/v1/auth/logout')
    },
    onSettled: () => {
      queryClient.clear()
      queryClient.setQueryData(queryKeys.me, null)
    },
  })
}
