import { useSearchParams } from 'react-router'

import { useMe } from '@/features/auth/useMe'
import { todayIn } from '@/lib/time'

import { pickCurrentSemester, useSemesters } from './useSchedule'

/** TZ пользователя (fallback — браузер, пока /me грузится). */
export function useTimeZone(): string {
  const { data: me } = useMe()
  return me?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
}

/** Семестры + выбранный (?semester=… в URL, по умолчанию — текущий по дате). */
export function useCurrentSemester() {
  const tz = useTimeZone()
  const today = todayIn(tz)
  const query = useSemesters()
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('semester')
  const semesters = query.data ?? []
  const semester =
    semesters.find((s) => s.id === selectedId) ?? pickCurrentSemester(semesters, today)
  const select = (id: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('semester', id)
        return next
      },
      { replace: true },
    )
  return { ...query, semesters, semester, select, today, tz }
}
