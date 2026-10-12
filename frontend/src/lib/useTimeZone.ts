import { useMe } from '@/features/auth/useMe'

/** TZ пользователя (fallback — браузер, пока /me грузится). */
export function useTimeZone(): string {
  const { data: me } = useMe()
  return me?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
}
