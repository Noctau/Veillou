import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '@/api/schema'

import { queryClient } from './queryClient'
import { queryKeys } from './queryKeys'

// Фронт и /api на одном origin (в dev — через proxy Vite), cookie сессии уходит сама.
export const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })

// Сессия истекла на любом запросе -> сбрасываем пользователя, RequireAuth уведёт на /login
const sessionMiddleware: Middleware = {
  onResponse({ request, response }) {
    if (response.status === 401 && !request.url.endsWith('/auth/login')) {
      queryClient.setQueryData(queryKeys.me, null)
    }
  },
}
api.use(sessionMiddleware)
