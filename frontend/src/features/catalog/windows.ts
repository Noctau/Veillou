import { WEEKDAYS_SHORT } from '@/lib/time'

import type { TimeWindow } from './useCatalog'

/** [1,2,3,4,5] → «пн–пт», [2,4] → «вт, чт», все → «каждый день». */
export function describeWeekdays(days: number[]): string {
  const sorted = [...days].sort((a, b) => a - b)
  if (sorted.length === 7) return 'каждый день'
  const short = (d: number) => WEEKDAYS_SHORT[d - 1].toLowerCase()
  const isRun = sorted.length >= 3 && sorted.every((d, i) => i === 0 || d === sorted[i - 1] + 1)
  if (isRun) return `${short(sorted[0])}–${short(sorted[sorted.length - 1])}`
  return sorted.map(short).join(', ')
}

/** «пн–пт 09:00–19:00»; через полночь — «… 07:00–01:00 (ночь)». */
export function describeWindow(w: TimeWindow): string {
  const night = w.end <= w.start ? ' (до утра)' : ''
  return `${describeWeekdays(w.weekdays)} ${w.start}–${w.end}${night}`
}

export function describeWindows(windows: TimeWindow[] | null | undefined): string {
  return windows?.length ? windows.map(describeWindow).join('; ') : 'как у типа'
}

export function windowsValid(value: TimeWindow[]): boolean {
  return value.every((w) => w.weekdays.length > 0 && w.start !== w.end)
}
