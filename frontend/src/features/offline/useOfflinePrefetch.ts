import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { attachmentsQueryOptions } from '@/features/attachments/useAttachments'
import { calendarQueryOptions } from '@/features/calendar/useCalendar'
import { noteQueryOptions, notesQueryOptions } from '@/features/notes/useNotes'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { FILES_CACHE, fileCacheKey } from '@/lib/pwa-shared'
import { addDaysIso, dayStartUtc, todayIn, weekMonday } from '@/lib/time'

/** Сколько последних конспектов держать открываемыми без сети. */
const RECENT_NOTES = 10
const MAX_WARM_IMAGES = 40

/** Окно календаря для офлайна: текущая и следующая неделя целиком (≥ 7 дней вперёд). */
export function offlineCalendarRange(today: string, tz: string) {
  const monday = weekMonday(today)
  return { from: dayStartUtc(monday, tz), to: dayStartUtc(addDaysIso(monday, 14), tz) }
}

/** Картинки, которых ещё нет в кэше SW, — догружаем фоном (SW сам положит их в кэш). */
async function warmImages(urls: string[]) {
  if (!('caches' in window) || !navigator.serviceWorker?.controller) return
  const cache = await caches.open(FILES_CACHE)
  let warmed = 0
  for (const url of urls) {
    if (warmed >= MAX_WARM_IMAGES) break
    const absolute = new URL(url, window.location.origin)
    if (await cache.match(fileCacheKey(absolute))) continue
    warmed++
    await fetch(absolute).catch(() => undefined)
  }
}

/**
 * Пока есть сеть, заранее грузит то, что должно открываться офлайн:
 * календарь на 7+ дней вперёд и последние конспекты со страницами.
 * Всё остальное (задания, предметы, ящик…) сохраняется по мере открытия экранов.
 */
export function useOfflinePrefetch(online: boolean) {
  const queryClient = useQueryClient()
  const tz = useTimeZone()
  const today = todayIn(tz)

  useEffect(() => {
    if (!online) return
    let cancelled = false
    const run = async () => {
      const { from, to } = offlineCalendarRange(today, tz)
      await queryClient.prefetchQuery(calendarQueryOptions(from, to))

      const notes = await queryClient.fetchQuery(notesQueryOptions())
      const recent = notes.slice(0, RECENT_NOTES)
      await Promise.all(recent.map((n) => queryClient.prefetchQuery(noteQueryOptions(n.id))))

      const withFiles = recent.filter((n) => n.attachments_count > 0)
      const lists = await Promise.all(
        withFiles.map((n) => queryClient.fetchQuery(attachmentsQueryOptions('note', n.id)).catch(() => [])),
      )
      if (cancelled) return
      const images = lists.flat().filter((a) => a.mime.startsWith('image/'))
      await warmImages(images.map((a) => a.url))
    }
    // Не мешаем первому экрану: стартуем, когда браузер освободится
    const timer = window.setTimeout(() => void run().catch(() => undefined), 2000)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [online, today, tz, queryClient])
}
