import { differenceInMinutes, parseISO } from 'date-fns'
import { CalendarCheckIcon, ClipboardCheckIcon, MapPinIcon, PlusIcon, TimerIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { type EventView, placeOf, timeRange, useEventView } from '@/features/calendar/eventUtils'
import { EventDetailsDialog } from '@/features/calendar/EventDetailsDialog'
import { EventDialog } from '@/features/calendar/EventDialog'
import { TodayProfileChip } from '@/features/dayprofiles/TodayProfileChip'
import { type CalendarEvent, useCalendar, useUpdateEvent } from '@/features/calendar/useCalendar'
import { cycleWeek } from '@/features/schedule/cycle'
import { useCurrentPeriod } from '@/features/schedule/useCurrentPeriod'
import { NoteForEventButton } from '@/features/notes/NoteForEventButton'
import { useNotes } from '@/features/notes/useNotes'
import { plural } from '@/features/plan/labels'
import { useAskFeel } from '@/features/plan/useAskFeel'
import { FreeDialog } from '@/features/review/FreeDialog'
import { DeadlinesCard } from '@/features/tasks/DeadlinesCard'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { NOW_NEXT_UI as N, SCHEDULE_UI } from '@/lib/terms'
import { addDaysIso, dayStartUtc, formatDay, isoWeekday, wallTime } from '@/lib/time'
import { cn } from '@/lib/utils'

import { useNow } from './useNow'

function inMinutes(minutes: number): string {
  if (minutes < 1) return 'сейчас'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} ч${m ? ` ${m} мин` : ''}` : `${m} мин`
}

// ---------- «Сейчас / Дальше» ----------

/** События типов с `show_now_next`: что идёт сейчас и что дальше. */
function NowNextCard({
  events,
  now,
  tz,
  dayOff,
  view,
  onOpen,
}: {
  events: CalendarEvent[]
  now: Date
  tz: string
  dayOff?: string
  view: EventView
  onOpen: (e: CalendarEvent) => void
}) {
  const live = events.filter((e) => e.status !== 'cancelled')
  const current = live.find((e) => parseISO(e.start) <= now && now < parseISO(e.end))
  const next = live.find((e) => parseISO(e.start) > now)
  const { data: notes } = useNotes({ event_id: current ? [current.id] : [] }, !!current)
  const notedEventIds = new Set(notes?.map((n) => n.event_id))

  if (!current && !next) {
    const text = dayOff ? N.dayOff(dayOff) : live.length ? N.over : N.empty
    return (
      <Card>
        <CardContent className="py-4 text-sm text-muted-foreground">{text}</CardContent>
      </Card>
    )
  }

  const row = (e: CalendarEvent, label: string, hint: string, withNote = false) => (
    <div className={cn('flex flex-col gap-2 border-l-4 pl-3', paletteColor(view.color(e)).border)}>
      <button type="button" onClick={() => onOpen(e)} className="flex w-full gap-3 text-left">
        <div className="flex-1">
          <div className="text-xs text-muted-foreground uppercase">{label}</div>
          <div className="text-lg leading-tight font-semibold">{e.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            {e.location && (
              <span className="flex items-center gap-1 text-base font-medium text-foreground">
                <MapPinIcon className="size-4" />
                {placeOf(e, view.typeOf(e))}
              </span>
            )}
            <span>{timeRange(e, tz)}</span>
            <span>{view.details(e, { withPlace: false })}</span>
          </div>
        </div>
        <div className="self-center text-right text-sm whitespace-nowrap text-muted-foreground">{hint}</div>
      </button>
      {withNote && <NoteForEventButton eventId={e.id} hasNote={notedEventIds.has(e.id)} variant="secondary" className="self-start" />}
    </div>
  )

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-4">
        {current && row(current, N.now, N.left(inMinutes(differenceInMinutes(parseISO(current.end), now))), !!current.area_id)}
        {next && row(next, current ? N.next : N.upcoming, N.inTime(inMinutes(differenceInMinutes(parseISO(next.start), now))))}
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
  view,
}: {
  event: CalendarEvent
  now: Date
  tz: string
  view: EventView
  onToggle: (e: CalendarEvent) => void
  onOpen: (e: CalendarEvent) => void
}) {
  const start = parseISO(event.start)
  const end = parseISO(event.end)
  const isNow = start <= now && now < end
  const past = end <= now
  const cancelled = event.status === 'cancelled'
  const done = event.status === 'done'
  const missed = event.status === 'missed'
  const details = view.details(event)

  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-lg px-2 py-2',
        isNow && 'bg-muted',
        (past || cancelled || done || missed) && 'opacity-60',
      )}
    >
      <span className="w-[5.5rem] shrink-0 text-xs text-muted-foreground tabular-nums">
        {wallTime(event.start, tz)}–{wallTime(event.end, tz)}
      </span>
      <span className={cn('h-8 w-1 shrink-0 rounded-full', paletteColor(view.color(event)).bg)} />
      <button type="button" onClick={() => onOpen(event)} className="min-w-0 flex-1 text-left">
        <span className={cn('block truncate text-sm font-medium', (cancelled || done) && 'line-through')}>
          {event.title}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {cancelled ? 'отменено' : missed ? 'не сделано' : details}
          {event.detached && !cancelled && ' · изменено'}
        </span>
      </button>
      {view.isDoable(event) && (
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

function ReviewLink({ to, icon: Icon, text }: { to: string; icon: typeof TimerIcon; text: string }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 text-sm font-medium hover:bg-accent"
    >
      <Icon className="size-5 shrink-0 text-primary" />
      {text}
    </Link>
  )
}

// ---------- экран ----------

export function TodayView() {
  const { period, today, tz } = useCurrentPeriod()
  const view = useEventView()
  const now = useNow()
  const from = dayStartUtc(today, tz)
  const to = dayStartUtc(addDaysIso(today, 1), tz)
  const { data, isPending, isError, error } = useCalendar(from, to)
  const update = useUpdateEvent()
  const [opened, setOpened] = useState<CalendarEvent | null>(null)
  const [creating, setCreating] = useState(false)
  const [free, setFree] = useState(false)

  const events = data?.events ?? []
  const nowNext = events.filter((e) => view.typeOf(e)?.show_now_next)
  const doable = events.filter(view.isDoable)
  const doneCount = doable.filter((e) => e.status === 'done').length
  // Гибкие блоки, которые уже начались, но не отмечены, — повод для разбора
  const unmarked = doable.filter((e) => !e.is_fixed && e.status === 'planned' && parseISO(e.start) <= now)
  const weekend = isoWeekday(today) >= 6
  const dayOff = data?.days_off[0]
  const inPeriod = period && period.cycle_weeks > 1 && period.start_date <= today && today <= period.end_date
  const week = inPeriod ? cycleWeek(today, period) : null

  const askFeel = useAskFeel()

  const toggle = (e: CalendarEvent) => {
    const status = e.status === 'done' ? 'planned' : 'done'
    update.mutate(
      { id: e.id, body: { status } },
      { onSuccess: () => status === 'done' && e.source_type === 'subtask' && e.source_id && askFeel(e.source_id) },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground first-letter:uppercase">
          {formatDay(today, { weekday: 'long', month: 'long' })}
        </span>
        {week && <span>· {SCHEDULE_UI.cycleWeek(week).toLowerCase()}</span>}
        <TodayProfileChip day={today} />
      </div>

      {isPending && <Skeleton className="h-28" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}

      {data && (
        <>
          {(nowNext.length > 0 || [...view.types.values()].some((t) => t.show_now_next)) && (
            <NowNextCard
              events={nowNext}
              now={now}
              tz={tz}
              dayOff={dayOff?.title || (dayOff && 'выходной')}
              view={view}
              onOpen={setOpened}
            />
          )}

          {doable.length > 0 && (
            <div className="flex items-center gap-3">
              <Progress value={(doneCount / doable.length) * 100} className="h-2 flex-1" aria-label="Прогресс дня" />
              <span className="text-sm text-muted-foreground tabular-nums">
                {doneCount} из {doable.length}
              </span>
            </div>
          )}

          {unmarked.length > 0 && (
            <ReviewLink
              to="/review"
              icon={ClipboardCheckIcon}
              text={`Не отмечено ${unmarked.length} ${plural(unmarked.length, 'блок', 'блока', 'блоков')} — разобрать`}
            />
          )}
          {weekend && <ReviewLink to="/review/week" icon={CalendarCheckIcon} text="Разбор недели: итоги и дела из ящика" />}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">День</CardTitle>
              <CardAction className="flex gap-1">
                <Button variant="ghost" size="sm" onClick={() => setFree(true)}>
                  <TimerIcon /> Есть время
                </Button>
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
                    <FeedRow key={e.id} event={e} now={now} tz={tz} onToggle={toggle} onOpen={setOpened} view={view} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <DeadlinesCard tz={tz} now={now} />
        </>
      )}

      <EventDetailsDialog event={opened} onOpenChange={(open) => !open && setOpened(null)} />
      <EventDialog open={creating} onOpenChange={setCreating} draft={{ date: today }} />
      <FreeDialog open={free} onOpenChange={setFree} />
    </div>
  )
}
