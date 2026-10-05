import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

/** Текущий пользователь; null — не вошла. */
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
