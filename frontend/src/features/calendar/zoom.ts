/**
 * Масштаб сетки «День / Неделя»: шаг слота и его высота. Чем крупнее, тем больше
 * пикселей на час — короткие блоки (15–30 мин) становятся читаемыми.
 */
export type ZoomLevel = { slot: string; slotMin: number; heightPx: number; label: string }

export const ZOOM_LEVELS: ZoomLevel[] = [
  { slot: '01:00:00', slotMin: 60, heightPx: 40, label: '50%' },
  { slot: '00:30:00', slotMin: 30, heightPx: 40, label: '100%' },
  { slot: '00:30:00', slotMin: 30, heightPx: 64, label: '160%' },
  { slot: '00:15:00', slotMin: 15, heightPx: 48, label: '240%' },
  { slot: '00:15:00', slotMin: 15, heightPx: 72, label: '360%' },
]

/** Как было до масштаба: слот 30 мин по 40 px. */
export const DEFAULT_ZOOM = 1

export function clampZoom(level: number | undefined): number {
  if (level === undefined || !Number.isInteger(level)) return DEFAULT_ZOOM
  return Math.min(Math.max(level, 0), ZOOM_LEVELS.length - 1)
}

/** Пикселей на минуту на этом масштабе. */
export function pxPerMinute(level: number): number {
  const z = ZOOM_LEVELS[clampZoom(level)]
  return z.heightPx / z.slotMin
}

/** Блок ниже этой высоты — в одну строку «время · название». */
export const SHORT_EVENT_PX = 36

export function isShortEvent(minutes: number, level: number): boolean {
  return minutes * pxPerMinute(level) < SHORT_EVENT_PX
}

/** Щипок двумя пальцами: во сколько раз изменилось расстояние → шаг масштаба (или 0). */
export function pinchStep(startDistance: number, distance: number): -1 | 0 | 1 {
  if (startDistance <= 0) return 0
  const ratio = distance / startDistance
  if (ratio >= 1.25) return 1
  if (ratio <= 0.8) return -1
  return 0
}
