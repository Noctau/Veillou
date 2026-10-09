import { describe, expect, it } from 'vitest'

import { errorCode, errorMessage } from './errors'

describe('ошибки API', () => {
  it('единый формат {error: {code, message}}', () => {
    const e = { error: { code: 'plan_stale', message: 'Устарело' } }
    expect(errorMessage(e)).toBe('Устарело')
    expect(errorCode(e)).toBe('plan_stale')
  })

  it('сеть и прочее', () => {
    expect(errorMessage(new TypeError('Failed to fetch'))).toBe('Нет связи с сервером')
    expect(errorMessage(new Error('x'))).toBe('x')
    expect(errorMessage(null, 'по умолчанию')).toBe('по умолчанию')
    expect(errorCode('x')).toBeUndefined()
  })
})

describe('ошибка валидации (422) — тот же формат', () => {
  it('message из бэкенда', () => {
    const e = { error: { code: 'validation_error', message: 'email: Field required' } }
    expect(errorMessage(e)).toBe('email: Field required')
    expect(errorCode(e)).toBe('validation_error')
  })
})
