/// <reference lib="webworker" />
/**
 * Service worker: оболочка приложения офлайн, кэш GET /api и файлов,
 * «Поделиться» (Web Share Target), Web Push и кнопки уведомлений.
 */
import { CacheableResponsePlugin } from 'workbox-cacheable-response'
import { ExpirationPlugin } from 'workbox-expiration'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { CacheFirst, NetworkFirst } from 'workbox-strategies'

import {
  API_CACHE,
  FILES_CACHE,
  fileCacheKey,
  pruneShares,
  saveShare,
  SHARE_PARAM,
  SHARE_TARGET_PATH,
} from '../lib/pwa-shared'

declare const self: ServiceWorkerGlobalScope

const DAY_SEC = 24 * 60 * 60

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.addEventListener('install', () => {
  void self.skipWaiting()
})
self.addEventListener('activate', (event) => {
  event.waitUntil(Promise.all([self.clients.claim(), pruneShares().catch(() => undefined)]))
})

// ---------- оболочка ----------

// Любой адрес приложения открывается из precache и без сети (в dev precache пустой)
if (import.meta.env.PROD) {
  registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), { denylist: [/^\/api\//] }))
}

// ---------- «Поделиться» ----------

// Android шлёт POST multipart (manifest.share_target). Кладём всё в IndexedDB и
// открываем быстрое добавление: файлы не пролезут ни в URL, ни в history.state.
registerRoute(
  ({ url }) => url.origin === self.location.origin && url.pathname === SHARE_TARGET_PATH,
  async ({ request }) => {
    const id = crypto.randomUUID()
    try {
      const form = await request.formData()
      const str = (name: string) => {
        const value = form.get(name)
        return typeof value === 'string' ? value : ''
      }
      const files = form.getAll('files').filter((f): f is File => f instanceof File && f.size > 0)
      await saveShare({ id, createdAt: Date.now(), title: str('title'), text: str('text'), url: str('url'), files })
    } catch {
      return Response.redirect('/add', 303)
    }
    return Response.redirect(`/add?${SHARE_PARAM}=${id}`, 303)
  },
  'POST',
)

// ---------- файлы ----------

// Картинки по подписанным ссылкам. Ключ — без подписи, но с версией содержимого (v=),
// поэтому можно брать из кэша сразу: офлайн откроется вчерашняя страница конспекта
// по сегодняшней ссылке, а повёрнутая страница придёт под новым ключом.
registerRoute(
  ({ url }) =>
    url.origin === self.location.origin && url.pathname.startsWith('/api/v1/files/') && !url.searchParams.has('download'),
  new CacheFirst({
    cacheName: FILES_CACHE,
    plugins: [
      {
        cacheKeyWillBeUsed: async ({ request }) => fileCacheKey(request.url),
        // PDF и прочее не кэшируем — только картинки
        cacheWillUpdate: async ({ response }) =>
          response.status === 200 && response.headers.get('Content-Type')?.startsWith('image/') ? response : null,
      },
      new ExpirationPlugin({ maxEntries: 400, maxAgeSeconds: 60 * DAY_SEC, purgeOnQuotaError: true }),
    ],
  }),
)

// ---------- API ----------

// Сеть первая: после мутаций TanStack Query перезапрашивает данные и должен получить свежие.
// Кэш — только когда сети нет (основной офлайн-слой — персист TanStack Query в IndexedDB).
const API_SKIP = ['/api/v1/auth/', '/api/v1/search', '/api/v1/files/']
registerRoute(
  ({ url }) =>
    url.origin === self.location.origin &&
    url.pathname.startsWith('/api/') &&
    !API_SKIP.some((prefix) => url.pathname.startsWith(prefix)),
  new NetworkFirst({
    cacheName: API_CACHE,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 300, maxAgeSeconds: 7 * DAY_SEC, purgeOnQuotaError: true }),
    ],
  }),
)

// ---------- push ----------

type PushAction = { action: string; title: string }
type PushData = {
  title: string
  body: string
  url: string
  tag: string | null
  actions: PushAction[]
  token: string | null
}

const ICON = '/pwa-192.png'
const BADGE = '/badge-96.png'

self.addEventListener('push', (event) => {
  let data: PushData
  try {
    data = event.data?.json() as PushData
  } catch {
    data = { title: 'Veillou', body: event.data?.text() ?? '', url: '/', tag: null, actions: [], token: null }
  }
  const options: NotificationOptions & { actions?: PushAction[]; renotify?: boolean } = {
    body: data.body,
    icon: ICON,
    badge: BADGE,
    tag: data.tag ?? undefined,
    renotify: !!data.tag,
    data: { url: data.url, token: data.token },
    // Кнопки показывает Android; на iPhone пуш просто открывает нужный экран
    actions: data.actions,
  }
  event.waitUntil(self.registration.showNotification(data.title, options))
})

async function openUrl(url: string) {
  const target = new URL(url, self.location.origin).href
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
  const existing = windows.find((w) => new URL(w.url).origin === self.location.origin)
  if (existing) {
    await existing.focus()
    return existing.navigate(target)
  }
  return self.clients.openWindow(target)
}

async function runAction(action: string, token: string, url: string) {
  try {
    const resp = await fetch('/api/v1/notifications/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, action }),
    })
    const body = (await resp.json()) as { message?: string; error?: { message: string } }
    const text = resp.ok ? body.message : body.error?.message
    await self.registration.showNotification(resp.ok ? 'Готово' : 'Не получилось', {
      body: text ?? '',
      icon: ICON,
      tag: 'action-result',
      data: { url },
    })
  } catch {
    // Нет сети — открываем приложение, там можно сделать то же руками
    await openUrl(url)
  }
}

self.addEventListener('notificationclick', (event) => {
  const { url = '/', token = null } = (event.notification.data ?? {}) as {
    url?: string
    token?: string | null
  }
  event.notification.close()
  if (event.action && token) {
    event.waitUntil(runAction(event.action, token, url))
  } else {
    event.waitUntil(openUrl(url))
  }
})
