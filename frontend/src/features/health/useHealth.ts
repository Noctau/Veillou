import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/health')
      if (error) throw error
      return data
    },
    refetchInterval: 60_000,
  })
}
