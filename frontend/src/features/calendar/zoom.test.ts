import { describe, expect, it } from 'vitest'

import { clampZoom, DEFAULT_ZOOM, isShortEvent, pinchStep, pxPerMinute, ZOOM_LEVELS } from './zoom'

describe('масштаб календаря', () => {
  it('по умолчанию — как раньше: 30 мин по 40 px', () => {
    expect(ZOOM_LEVELS[DEFAULT_ZOOM]).toMatchObject({ slotMin: 30, heightPx: 40 })
    expect(pxPerMinute(DEFAULT_ZOOM)).toBeCloseTo(4 / 3)
  })

  it('уровни идут по возрастанию пикселей на час', () => {
    const perHour = ZOOM_LEVELS.map((_, i) => pxPerMinute(i) * 60)
    expect([...perHour].sort((a, b) => a - b)).toEqual(perHour)
    expect(new Set(perHour).size).toBe(perHour.length)
  })

  it('зажимает уровень в границы', () => {
    expect(clampZoom(undefined)).toBe(DEFAULT_ZOOM)
    expect(clampZoom(-3)).toBe(0)
    expect(clampZoom(99)).toBe(ZOOM_LEVELS.length - 1)
    expect(clampZoom(1.5)).toBe(DEFAULT_ZOOM)
  })

  it('15-минутный блок короткий на обычном масштабе и читаемый на крупном', () => {
    expect(isShortEvent(15, DEFAULT_ZOOM)).toBe(true)
    expect(isShortEvent(15, ZOOM_LEVELS.length - 1)).toBe(false)
    expect(isShortEvent(90, DEFAULT_ZOOM)).toBe(false)
  })

  it('щипок: развели пальцы — крупнее, свели — мельче', () => {
    expect(pinchStep(100, 130)).toBe(1)
    expect(pinchStep(100, 75)).toBe(-1)
    expect(pinchStep(100, 105)).toBe(0)
    expect(pinchStep(0, 50)).toBe(0)
  })
})
