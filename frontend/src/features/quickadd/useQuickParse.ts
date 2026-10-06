import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export type QuickParse = components['schemas']['QuickParseRead']
export type KindHint = components['schemas']['KindHint']

const DEBOUNCE_MS = 200

async function fetchParse(text: string): Promise<QuickParse> {
  const { data, error } = await api.POST('/api/v1/quick-add/parse', { body: { text } })
  if (error) throw error
  return data
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

/** Разбор строки «на лету» (с задержкой 200 мс). Старый результат держится, пока грузится новый. */
export function useQuickParse(text: string) {
  const debounced = useDebounced(text.trim(), DEBOUNCE_MS)
  return useQuery({
    queryKey: queryKeys.quickParse(debounced),
    enabled: debounced.length > 0,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    queryFn: () => fetchParse(debounced),
  })
}

/** Разбор для сохранения: свежий, даже если превью ещё не успело обновиться. */
export function useParseNow() {
  const queryClient = useQueryClient()
  return (text: string) =>
    queryClient.fetchQuery({
      queryKey: queryKeys.quickParse(text.trim()),
      staleTime: 60_000,
      queryFn: () => fetchParse(text.trim()),
    })
}
