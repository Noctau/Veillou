import { useMe, useUpdateMe } from '@/features/auth/useMe'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ONBOARDING_UI as T } from '@/lib/terms'

function zones(current: string): string[] {
  const all = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone
  return [...new Set([current, browser, ...all])].filter(Boolean)
}

/** Часовой пояс пользователя: по умолчанию — сервера, подсказка — пояс браузера. */
export function TimezonePicker() {
  const { data: me } = useMe()
  const update = useUpdateMe()
  if (!me) return <Skeleton className="h-16" />
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone
  return (
    <Field>
      <FieldLabel htmlFor="tz">{T.timezone}</FieldLabel>
      <Select value={me.timezone} onValueChange={(timezone) => update.mutate({ timezone })}>
        <SelectTrigger id="tz" className="w-full sm:w-80">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-80">
          {zones(me.timezone).map((z) => (
            <SelectItem key={z} value={z}>
              {z.replaceAll('_', ' ')}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldDescription>
        {browser && browser !== me.timezone ? T.timezoneBrowser(browser.replaceAll('_', ' ')) : T.timezoneHint}
      </FieldDescription>
    </Field>
  )
}
