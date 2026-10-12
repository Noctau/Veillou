import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

/** Текущий пользователь; null — входа нет. */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me')
      if (response.status === 401) return null
      if (error) throw error
      return data
    },
    staleTime: 5 * 60_000,
    retry: false,
  })
}

/** Часовой пояс: расписание пересобирается на сервере — календарь перечитываем. */
export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['UserUpdate']) => {
      const { data, error } = await api.PATCH('/api/v1/me', { body })
      if (error) throw error
      return data
    },
    onSuccess: (me) => {
      queryClient.setQueryData(queryKeys.me, me)
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
