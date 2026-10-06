import { BellIcon, BellOffIcon, SendIcon, SmartphoneIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatDay, todayIn, wallDate, wallTime, addDaysIso } from '@/lib/time'

import {
  pushUnsupportedReason,
  useBrowserPush,
  usePushConfig,
  useSendTestNotification,
  useSubscribePush,
  useUnsubscribePush,
  useUpcomingReminders,
} from './usePush'

const CHANNEL_LABEL = { push: 'push', telegram: 'Telegram' } as const

function PushDevice() {
  const config = usePushConfig()
  const browser = useBrowserPush()
  const subscribe = useSubscribePush()
  const unsubscribe = useUnsubscribePush()
  const unsupported = pushUnsupportedReason()

  if (unsupported) return <p className="text-sm text-muted-foreground">{unsupported}</p>
  if (config.isPending || browser.isPending) return <Skeleton className="h-9 w-56" />
  if (!config.data?.vapid_public_key) {
    return <p className="text-sm text-muted-foreground">Push не настроен на сервере (нет VAPID-ключей).</p>
  }

  const subscribed =
    !!browser.data?.endpoint && config.data.subscriptions.length > 0 && browser.data.permission === 'granted'
  const denied = browser.data?.permission === 'denied'
  const busy = subscribe.isPending || unsubscribe.isPending
  const key = config.data.vapid_public_key

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-2 text-sm">
          {subscribed ? <BellIcon className="size-4 text-primary" /> : <BellOffIcon className="size-4 text-muted-foreground" />}
          {subscribed ? 'Push включён на этом устройстве' : 'Push на этом устройстве выключен'}
        </span>
        {subscribed ? (
          <Button variant="outline" size="sm" className="ml-auto" disabled={busy} onClick={() => unsubscribe.mutate()}>
            Выключить
          </Button>
        ) : (
          <Button size="sm" className="ml-auto" disabled={busy || denied} onClick={() => subscribe.mutate(key)}>
            Включить
          </Button>
        )}
      </div>
      {denied && (
        <p className="text-sm text-destructive">
          Уведомления запрещены в браузере. Разрешите их в настройках сайта и обновите страницу.
        </p>
      )}
      {config.data.subscriptions.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
          {config.data.subscriptions.map((s) => (
            <li key={s.id} className="flex items-center gap-2">
              <SmartphoneIcon className="size-3.5" />
              {s.device_name || 'Устройство'}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Upcoming() {
  const tz = useTimeZone()
  const { data, isPending } = useUpcomingReminders()
  if (isPending) return <Skeleton className="h-24" />
  if (!data?.length) return <p className="text-sm text-muted-foreground">Пока ничего не запланировано.</p>

  const today = todayIn(tz)
  const dayLabel = (iso: string) => {
    const day = wallDate(iso, tz)
    if (day === today) return 'сегодня'
    if (day === addDaysIso(today, 1)) return 'завтра'
    return formatDay(day)
  }

  return (
    <ul className="flex flex-col gap-2">
      {data.slice(0, 8).map((r) => (
        <li key={r.id} className="flex items-baseline gap-3 text-sm">
          <span className="w-32 shrink-0 text-muted-foreground tabular-nums">
            {dayLabel(r.fire_at)} {wallTime(r.fire_at, tz)}
          </span>
          <span className="min-w-0 flex-1 truncate">{r.label}</span>
          <span className="hidden gap-1 sm:flex">
            {r.channels.map((c) => (
              <Badge key={c} variant="secondary">
                {CHANNEL_LABEL[c]}
              </Badge>
            ))}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function NotificationsSection() {
  const test = useSendTestNotification()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Уведомления</CardTitle>
        <CardDescription>Push на телефон и ноутбук. Telegram подключается ниже.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        <PushDevice />
        <Button variant="outline" size="sm" className="self-start" disabled={test.isPending} onClick={() => test.mutate()}>
          <SendIcon />
          Проверить уведомления
        </Button>
        <Separator />
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Ближайшие напоминания</h3>
          <Upcoming />
        </div>
      </CardContent>
    </Card>
  )
}
