import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

/** Почему push недоступен в этом браузере (null — доступен). */
export function pushUnsupportedReason(): string | null {
  if (!window.isSecureContext) return 'Push работает только по HTTPS (или на localhost).'
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return 'Этот браузер не поддерживает push. На iPhone сначала добавьте приложение на экран «Домой».'
  }
  return null
}

const SW_TIMEOUT_MS = 10_000

async function registration(): Promise<ServiceWorkerRegistration> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Service worker не запустился — обновите страницу')), SW_TIMEOUT_MS),
  )
  return Promise.race([navigator.serviceWorker.ready, timeout])
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = (value + '='.repeat((4 - (value.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

function deviceName(): string {
  const ua = navigator.userAgent
  const os = /Android/.test(ua)
    ? 'Android'
    : /iPhone|iPad/.test(ua)
      ? 'iPhone'
      : /Mac/.test(ua)
        ? 'Mac'
        : /Windows/.test(ua)
          ? 'Windows'
          : 'Linux'
  const browser = /Firefox/.test(ua) ? 'Firefox' : /Edg\//.test(ua) ? 'Edge' : /Chrome/.test(ua) ? 'Chrome' : 'Safari'
  return `${os} · ${browser}`
}

/** Подписки пользователя на сервере и публичный VAPID-ключ. */
export function usePushConfig() {
  return useQuery({
    queryKey: queryKeys.push,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/me/push')
      if (error) throw error
      return data
    },
  })
}

/** Состояние этого браузера: разрешение и текущая подписка. */
export function useBrowserPush() {
  return useQuery({
    queryKey: queryKeys.pushBrowser,
    enabled: pushUnsupportedReason() === null,
    queryFn: async () => {
      const reg = await registration()
      const sub = await reg.pushManager.getSubscription()
      return { permission: Notification.permission, endpoint: sub?.endpoint ?? null }
    },
  })
}

export function useSubscribePush() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (vapidKey: string) => {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        throw new Error('Уведомления запрещены. Разрешите их в настройках сайта в браузере.')
      }
      const reg = await registration()
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64UrlToBytes(vapidKey),
        }))
      const json = sub.toJSON()
      const { error } = await api.POST('/api/v1/me/push/subscriptions', {
        body: {
          endpoint: sub.endpoint,
          keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
          device_name: deviceName(),
        },
      })
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.push })
      queryClient.invalidateQueries({ queryKey: queryKeys.pushBrowser })
      toast.success('Push включён на этом устройстве')
    },
    onError: (error) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pushBrowser })
      toast.error(errorMessage(error))
    },
  })
}

export function useUnsubscribePush() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const reg = await registration()
      const sub = await reg.pushManager.getSubscription()
      if (!sub) return
      const { error } = await api.POST('/api/v1/me/push/unsubscribe', { body: { endpoint: sub.endpoint } })
      if (error) throw error
      await sub.unsubscribe()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.push })
      queryClient.invalidateQueries({ queryKey: queryKeys.pushBrowser })
      toast.success('Push выключен на этом устройстве')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useSendTestNotification() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/me/notifications/test')
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      const ready = data.channels.filter((c) => c.ready)
      const notReady = data.channels.filter((c) => !c.ready)
      if (ready.length === 0) {
        toast.error('Некуда отправить', { description: notReady.map((c) => c.reason).join('. ') })
        return
      }
      toast.success('Отправлено — придёт в течение минуты', {
        description: notReady.length ? notReady.map((c) => c.reason).join('. ') : undefined,
      })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpcomingReminders() {
  return useQuery({
    queryKey: queryKeys.reminders,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/me/reminders')
      if (error) throw error
      return data
    },
  })
}
