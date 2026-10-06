/// <reference lib="webworker" />
/**
 * Service worker: Web Push и кнопки уведомлений.
 * Кэш оболочки и офлайн-чтение — M7.1 (сейчас только precache сборки).
 */
import { precacheAndRoute } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

precacheAndRoute(self.__WB_MANIFEST)

self.addEventListener('install', () => {
  void self.skipWaiting()
})
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

type PushAction = { action: string; title: string }
type PushData = {
  title: string
  body: string
  url: string
  tag: string | null
  actions: PushAction[]
  token: string | null
}

const ICON = '/favicon.svg'

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
    badge: ICON,
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
