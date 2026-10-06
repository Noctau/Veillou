import { differenceInMinutes, parseISO } from 'date-fns'
import { MapPinIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { classDetails, eventColor, isDoable, timeRange } from '@/features/calendar/eventUtils'
import { EventDetailsDialog } from '@/features/calendar/EventDetailsDialog'
import { PersonalEventDialog } from '@/features/calendar/PersonalEventDialog'
import { type CalendarEvent, useCalendar, useUpdateEvent } from '@/features/calendar/useCalendar'
import { PARITY_LABEL, weekParity } from '@/features/schedule/parity'
import { useCurrentSemester } from '@/features/schedule/useCurrentSemester'
import { DeadlinesCard } from '@/features/tasks/DeadlinesCard'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { addDaysIso, dayStartUtc, formatDay, wallTime } from '@/lib/time'
import { cn } from '@/lib/utils'

import { useNow } from './useNow'

function inMinutes(minutes: number): string {
  if (minutes < 1) return 'сейчас'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} ч${m ? ` ${m} мин` : ''}` : `${m} мин`
}

// ---------- текущая / следующая пара ----------

function ClassNowCard({
  classes,
  now,
  tz,
  dayOff,
  onOpen,
}: {
  classes: CalendarEvent[]
  now: Date
  tz: string
  dayOff?: string
  onOpen: (e: CalendarEvent) => void
}) {
  const live = classes.filter((e) => e.status !== 'cancelled')
  const current = live.find((e) => parseISO(e.start) <= now && now < parseISO(e.end))
  const next = live.find((e) => parseISO(e.start) > now)

  if (!current && !next) {
    const text = dayOff
      ? `Сегодня без пар: ${dayOff}`
      : live.length
        ? 'Пары на сегодня закончились'
        : 'Сегодня пар нет'
    return (
      <Card>
        <CardContent className="py-4 text-sm text-muted-foreground">{text}</CardContent>
      </Card>
    )
  }

  const row = (e: CalendarEvent, label: string, hint: string) => (
    <button
      type="button"
      onClick={() => onOpen(e)}
      className={cn('flex w-full gap-3 border-l-4 pl-3 text-left', paletteColor(eventColor(e)).border)}
    >
      <div className="flex-1">
        <div className="text-xs text-muted-foreground uppercase">{label}</div>
        <div className="text-lg leading-tight font-semibold">{e.title}</div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
          {e.location && (
            <span className="flex items-center gap-1 text-base font-medium text-foreground">
              <MapPinIcon className="size-4" />
              {e.location}
            </span>
          )}
          <span>{timeRange(e, tz)}</span>
          <span>{classDetails({ ...e, location: null })}</span>
        </div>
      </div>
      <div className="self-center text-right text-sm whitespace-nowrap text-muted-foreground">{hint}</div>
    </button>
  )

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-4">
        {current && row(current, 'Сейчас', `ещё ${inMinutes(differenceInMinutes(parseISO(current.end), now))}`)}
        {next &&
          row(next, current ? 'Дальше' : 'Следующая', `через ${inMinutes(differenceInMinutes(parseISO(next.start), now))}`)}
      </CardContent>
    </Card>
  )
}

// ---------- лента дня ----------

function FeedRow({
  event,
  now,
  tz,
  onToggle,
  onOpen,
}: {
  event: CalendarEvent
  now: Date
  tz: string
  onToggle: (e: CalendarEvent) => void
  onOpen: (e: CalendarEvent) => void
}) {
  const start = parseISO(event.start)
  const end = parseISO(event.end)
  const isNow = start <= now && now < end
  const past = end <= now
  const cancelled = event.status === 'cancelled'
  const done = event.status === 'done'
  const details = event.kind === 'class' ? classDetails(event) : event.location

  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-lg px-2 py-2',
        isNow && 'bg-muted',
        (past || cancelled || done) && 'opacity-60',
      )}
    >
      <span className="w-[5.5rem] shrink-0 text-xs text-muted-foreground tabular-nums">
        {wallTime(event.start, tz)}–{wallTime(event.end, tz)}
      </span>
      <span className={cn('h-8 w-1 shrink-0 rounded-full', paletteColor(eventColor(event)).bg)} />
      <button type="button" onClick={() => onOpen(event)} className="min-w-0 flex-1 text-left">
        <span className={cn('block truncate text-sm font-medium', (cancelled || done) && 'line-through')}>
          {event.title}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {cancelled ? 'отменено' : details}
          {event.detached && !cancelled && ' · изменено'}
        </span>
      </button>
      {isDoable(event) && (
        <Checkbox
          aria-label={done ? 'Не сделано' : 'Сделано'}
          checked={done}
          onCheckedChange={() => onToggle(event)}
          className="size-5"
        />
      )}
    </li>
  )
}

// ---------- экран ----------

export function TodayView() {
  const { semester, today, tz } = useCurrentSemester()
  const now = useNow()
  const from = dayStartUtc(today, tz)
  const to = dayStartUtc(addDaysIso(today, 1), tz)
  const { data, isPending, isError, error } = useCalendar(from, to)
  const update = useUpdateEvent()
  const [opened, setOpened] = useState<CalendarEvent | null>(null)
  const [creating, setCreating] = useState(false)

  const events = data?.events ?? []
  const classes = events.filter((e) => e.kind === 'class')
  const doable = events.filter(isDoable)
  const doneCount = doable.filter((e) => e.status === 'done').length
  const dayOff = data?.days_off[0]
  const inClasses = semester && semester.start_date <= today && today <= semester.classes_end
  const parity = inClasses ? weekParity(today, semester.start_date, semester.first_week_parity) : null

  const toggle = (e: CalendarEvent) =>
    update.mutate({ id: e.id, body: { status: e.status === 'done' ? 'planned' : 'done' } })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground first-letter:uppercase">
          {formatDay(today, { weekday: 'long', month: 'long' })}
        </span>
        {parity && <span>· {PARITY_LABEL[parity].toLowerCase()}</span>}
      </div>

      {isPending && <Skeleton className="h-28" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}

      {data && (
        <>
          <ClassNowCard classes={classes} now={now} tz={tz} dayOff={dayOff?.title || (dayOff && 'выходной')} onOpen={setOpened} />

          {doable.length > 0 && (
            <div className="flex items-center gap-3">
              <Progress value={(doneCount / doable.length) * 100} className="h-2 flex-1" aria-label="Прогресс дня" />
              <span className="text-sm text-muted-foreground tabular-nums">
                {doneCount} из {doable.length}
              </span>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">День</CardTitle>
              <CardAction>
                <Button variant="ghost" size="sm" onClick={() => setCreating(true)}>
                  <PlusIcon /> Событие
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="pt-2">
              {events.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">Пусто — свободный день.</p>
              ) : (
                <ul className="flex flex-col">
                  {events.map((e) => (
                    <FeedRow key={e.id} event={e} now={now} tz={tz} onToggle={toggle} onOpen={setOpened} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <DeadlinesCard tz={tz} now={now} />
        </>
      )}

      <EventDetailsDialog event={opened} onOpenChange={(open) => !open && setOpened(null)} />
      <PersonalEventDialog open={creating} onOpenChange={setCreating} draft={{ date: today }} />
    </div>
  )
}
