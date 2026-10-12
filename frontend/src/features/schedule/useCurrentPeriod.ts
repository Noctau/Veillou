import { useSearchParams } from 'react-router'

import { todayIn } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'

import { pickCurrentPeriod, usePeriods } from './useSchedule'

/** «Без периода» в выборе периода. */
export const NO_PERIOD = 'none'

/**
 * Периоды + выбранный (?period=… в URL, по умолчанию — текущий по дате).
 * `period` — undefined, если выбрано «Без периода» или периодов нет.
 */
export function useCurrentPeriod() {
  const tz = useTimeZone()
  const today = todayIn(tz)
  const query = usePeriods()
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('period')
  const periods = query.data ?? []
  const period =
    selectedId === NO_PERIOD
      ? undefined
      : (periods.find((p) => p.id === selectedId) ?? pickCurrentPeriod(periods, today))
  const select = (id: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('period', id)
        return next
      },
      { replace: true },
    )
  return { ...query, periods, period, select, today, tz }
}
