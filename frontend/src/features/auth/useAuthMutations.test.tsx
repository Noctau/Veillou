import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'

import { useLogout } from './useAuthMutations'

vi.mock('@/lib/persist', () => ({ clearOfflineData: vi.fn(async () => undefined) }))

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

function mockPush(subscription: { endpoint: string; unsubscribe: () => Promise<boolean> } | null) {
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
  Object.defineProperty(window, 'PushManager', { value: class {}, configurable: true })
  Object.defineProperty(window, 'Notification', { value: class {}, configurable: true })
  Object.defineProperty(navigator, 'serviceWorker', {
    value: { ready: Promise.resolve({ pushManager: { getSubscription: async () => subscription } }) },
    configurable: true,
  })
}

describe('useLogout (M-03)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'POST').mockResolvedValue({ data: undefined, error: undefined, response: new Response() } as never)
  })

  it('отписывает это устройство от push до выхода', async () => {
    const unsubscribe = vi.fn(async () => true)
    mockPush({ endpoint: 'https://fcm.googleapis.com/fcm/send/abc', unsubscribe })
    const { result } = renderHook(() => useLogout(), { wrapper })

    await result.current.mutateAsync()

    const calls = vi.mocked(api.POST).mock.calls.map((c) => c[0])
    expect(calls).toEqual(['/api/v1/me/push/unsubscribe', '/api/v1/auth/logout'])
    expect(vi.mocked(api.POST).mock.calls[0][1]).toEqual({
      body: { endpoint: 'https://fcm.googleapis.com/fcm/send/abc' },
    })
    expect(unsubscribe).toHaveBeenCalled()
  })

  it('выходит, даже если подписки нет', async () => {
    mockPush(null)
    const { result } = renderHook(() => useLogout(), { wrapper })
    await result.current.mutateAsync()
    expect(vi.mocked(api.POST).mock.calls.map((c) => c[0])).toEqual(['/api/v1/auth/logout'])
  })
})
