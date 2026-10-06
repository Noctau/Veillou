import { QueryClient } from '@tanstack/react-query'

/** Сколько живут данные для офлайна (персист в IndexedDB, см. lib/persist.ts). */
export const OFFLINE_MAX_AGE_MS = 7 * 24 * 60 * 60_000

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Не меньше срока персиста: иначе неиспользуемый запрос выпадет из памяти и из IndexedDB
      gcTime: OFFLINE_MAX_AGE_MS,
      retry: 1,
      refetchOnWindowFocus: true,
    },
    mutations: {
      // Офлайн — только чтение: без сети запись сразу падает с «Нет связи с сервером»
      // (а не висит в памяти до появления сети и не теряется молча при закрытии)
      networkMode: 'always',
    },
  },
})
