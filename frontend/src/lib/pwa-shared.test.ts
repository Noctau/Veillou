import { describe, expect, it, vi } from 'vitest'

vi.mock('idb-keyval', () => ({
  createStore: vi.fn(),
  del: vi.fn(),
  entries: vi.fn(),
  get: vi.fn(),
  set: vi.fn(),
}))

const { fileCacheKey } = await import('./pwa-shared')

describe('ключ кэша файла', () => {
  it('без подписи, с версией содержимого', () => {
    const signed = 'https://app.test/api/v1/files/abc?exp=1&sig=deadbeef&v=1234'
    expect(fileCacheKey(signed)).toBe('https://app.test/api/v1/files/abc?v=1234')
    const other = 'https://app.test/api/v1/files/abc?exp=2&sig=cafe&v=1234'
    expect(fileCacheKey(other)).toBe(fileCacheKey(signed))
    expect(fileCacheKey(`${signed}&download=1`)).toBe('https://app.test/api/v1/files/abc?v=1234&download=1')
  })
})
