import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export type SearchResults = components['schemas']['SearchResults']
export type NoteHit = components['schemas']['NoteHit']

// Маркеры совпадений в сниппете (как в backend/app/domain/search.py)
export const HIT_START = '\u0002'
export const HIT_END = '\u0003'

const DEBOUNCE_MS = 250

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

/** Поиск по конспектам и литературе по мере набора. Пустая строка — запроса нет. */
export function useSearch(text: string, subjectId?: string) {
  const q = useDebounced(text.trim(), DEBOUNCE_MS)
  return useQuery({
    queryKey: queryKeys.search(q, subjectId),
    enabled: q.length > 0,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/search', {
        params: { query: { q, subject_id: subjectId } },
      })
      if (error) throw error
      return data
    },
  })
}
