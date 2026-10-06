/**
 * Офлайн-чтение: кэш TanStack Query живёт в IndexedDB 7 дней.
 * Ключ сброса — хэш OpenAPI-схемы: после деплоя с новым API старый кэш не подхватывается.
 */
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister'
import type { PersistQueryClientOptions } from '@tanstack/react-query-persist-client'
import { createStore, del, get, set } from 'idb-keyval'

import { queryClient, OFFLINE_MAX_AGE_MS } from './queryClient'
import { API_CACHE, FILES_CACHE } from './pwa-shared'

const store = createStore('veillou-query', 'cache')

const persister = createAsyncStoragePersister({
  key: 'veillou',
  throttleTime: 1000,
  storage: {
    getItem: (key) => get<string>(key, store),
    setItem: (key, value: string) => set(key, value, store),
    removeItem: (key) => del(key, store),
  },
})

// Что не нужно офлайн: живой парс строки, поиск, состояние push в этом браузере
const SKIP_PERSIST = new Set(['quick-parse', 'search', 'push-browser', 'health'])

export const persistOptions: Omit<PersistQueryClientOptions, 'queryClient'> = {
  persister,
  maxAge: OFFLINE_MAX_AGE_MS,
  buster: __API_SCHEMA_HASH__,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.state.status === 'success' &&
      !SKIP_PERSIST.has(String(query.queryKey[0])) &&
      // «Не вошла» не запоминаем: иначе вход в другой вкладке не виден до устаревания /me
      query.state.data !== null,
  },
}

/** При выходе: ничего личного не остаётся ни в памяти, ни в IndexedDB, ни в кэше SW. */
export async function clearOfflineData(): Promise<void> {
  queryClient.clear()
  await Promise.allSettled([
    persister.removeClient(),
    ...('caches' in window ? [caches.delete(API_CACHE), caches.delete(FILES_CACHE)] : []),
  ])
}
