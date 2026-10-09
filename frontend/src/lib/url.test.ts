import { describe, expect, it } from 'vitest'

import { normalizeUrl, safeNext } from './url'

describe('normalizeUrl', () => {
  it('дописывает https и принимает только http(s)', () => {
    expect(normalizeUrl(' example.com/a ')).toBe('https://example.com/a')
    expect(normalizeUrl('http://x.ru')).toBe('http://x.ru/')
    expect(normalizeUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeUrl('ftp://x.ru')).toBeNull()
    expect(normalizeUrl('localhost')).toBeNull()
    expect(normalizeUrl('')).toBeNull()
  })
})

describe('safeNext', () => {
  it('только пути внутри приложения', () => {
    expect(safeNext('/tasks/1?x=2')).toBe('/tasks/1?x=2')
    expect(safeNext('//evil.com')).toBe('/')
    expect(safeNext('/\\evil.com')).toBe('/')
    expect(safeNext('https://evil.com')).toBe('/')
    expect(safeNext(null)).toBe('/')
  })
})
