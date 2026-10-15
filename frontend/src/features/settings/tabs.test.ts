import { describe, expect, it } from 'vitest'

import { SETTINGS_TABS, tabFromParam } from './tabs'

describe('вкладки настроек', () => {
  it('без параметра или с неизвестным — первая вкладка', () => {
    expect(tabFromParam(null)).toBe('profile')
    expect(tabFromParam('nope')).toBe('profile')
  })

  it('по параметру — нужная', () => {
    for (const t of SETTINGS_TABS) expect(tabFromParam(t.id)).toBe(t.id)
  })

  it('id вкладок уникальны', () => {
    expect(new Set(SETTINGS_TABS.map((t) => t.id)).size).toBe(SETTINGS_TABS.length)
  })
})
