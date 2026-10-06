import { useEffect, useState } from 'react'

/** Текущее время, обновляется раз в `intervalMs` (для «сейчас идёт», «через 10 мин»). */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
