import { parseISO } from 'date-fns'
import { CheckIcon, MapPinIcon } from 'lucide-react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { classDetails, timeRange } from '@/features/calendar/eventUtils'
import { type CalendarEvent, useCalendar } from '@/features/calendar/useCalendar'
import { NoteForEventButton } from '@/features/notes/NoteForEventButton'
import { useNotes } from '@/features/notes/useNotes'
import { type ClassRule, useBells, useClassRules } from '@/features/schedule/useSchedule'
import { useCurrentSemester } from '@/features/schedule/useCurrentSemester'
import { useNow } from '@/features/today/useNow'
import { AREAS_UI as T, CLASS_TYPE_LABEL, RULE_PARITY_LABEL } from '@/lib/terms'
import { addDaysIso, dayStartUtc, formatDay, WEEKDAYS_SHORT, wallDate } from '@/lib/time'
import { cn } from '@/lib/utils'

import type { Area } from './useAreas'

const PAST_DAYS = 21
const AHEAD_DAYS = 14
const PAST_SHOWN = 6
const AHEAD_SHOWN = 3

function RulesList({ area }: { area: Area }) {
  const { data: rules, isPending } = useClassRules(area.period_id ?? undefined)
  const { data: bells } = useBells(area.period_id ?? undefined)
  const own = (rules ?? [])
    .filter((r) => r.area_id === area.id)
    .sort((a, b) => a.weekday - b.weekday || (a.pair_number ?? 0) - (b.pair_number ?? 0))

  const time = (r: ClassRule) => {
    if (r.start_time && r.end_time) return `${r.start_time}–${r.end_time}`
    const schedule = bells?.find((b) => b.weekday === r.weekday) ?? bells?.find((b) => b.weekday === null)
    const slot = schedule?.slots.find((s) => s.number === r.pair_number)
    return slot ? `${slot.start}–${slot.end}` : ''
  }

  if (!area.period_id) return null
  if (isPending) return <Skeleton className="h-16" />
  if (!own.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {T.noRules}{' '}
        <Link to="/areas?tab=schedule" className="text-primary underline-offset-4 hover:underline">
          {T.scheduleLink}
        </Link>
        .
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {own.map((r) => (
        <li key={r.id} className="flex flex-wrap items-baseline gap-x-2">
          <span className="w-6 font-medium">{WEEKDAYS_SHORT[r.weekday - 1]}</span>
          {r.pair_number && <span>{T.slot(r.pair_number)}</span>}
          <span className="text-muted-foreground tabular-nums">{time(r)}</span>
          <span className="text-muted-foreground">
            {[
              r.parity !== 'all' && RULE_PARITY_LABEL[r.parity].toLowerCase(),
              CLASS_TYPE_LABEL[r.class_type],
              r.location,
              r.teacher,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </li>
      ))}
    </ul>
  )
}

function OccurrenceRow({ event, tz, noteId }: { event: CalendarEvent; tz: string; noteId?: string }) {
  const cancelled = event.status === 'cancelled'
  return (
    <li className={cn('flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2', cancelled && 'opacity-60')}>
      <div className="min-w-0 flex-1">
        <div className={cn('text-sm font-medium first-letter:uppercase', cancelled && 'line-through')}>
          {formatDay(wallDate(event.start, tz), { weekday: 'long', month: 'long' })}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <span className="tabular-nums">{timeRange(event, tz)}</span>
          {event.location && (
            <span className="flex items-center gap-0.5">
              <MapPinIcon className="size-3" />
              {event.location}
            </span>
          )}
          <span>{cancelled ? T.cancelled : classDetails({ ...event, location: null })}</span>
        </div>
      </div>
      {noteId ? (
        <Link
          to={`/notes/${noteId}`}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-sm text-primary hover:bg-muted"
        >
          <CheckIcon className="size-4" /> {T.note}
        </Link>
      ) : (
        !cancelled && <NoteForEventButton eventId={event.id} variant="ghost" label={T.note} />
      )}
    </li>
  )
}

/** Раздел «Расписание» сферы: сетка, недавние занятия (с конспектами) и ближайшие. */
export function AreaSchedule({ area }: { area: Area }) {
  const { today, tz } = useCurrentSemester()
  const from = dayStartUtc(addDaysIso(today, -PAST_DAYS), tz)
  const to = dayStartUtc(addDaysIso(today, AHEAD_DAYS + 1), tz)
  const { data, isPending } = useCalendar(from, to)
  const { data: notes } = useNotes({ area_id: area.id })
  const noteByEvent = new Map(notes?.filter((n) => n.event_id).map((n) => [n.event_id!, n.id]))

  const now = useNow()
  // Жёсткие события сферы (занятия по сетке)
  const occurrences = (data?.events ?? []).filter((e) => e.kind === 'class' && e.area_id === area.id)
  const past = occurrences
    .filter((e) => parseISO(e.start) <= now)
    .reverse()
    .slice(0, PAST_SHOWN)
  const ahead = occurrences.filter((e) => parseISO(e.start) > now).slice(0, AHEAD_SHOWN)

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">{T.rules}</h3>
        <RulesList area={area} />
      </section>

      {isPending && <Skeleton className="h-24" />}
      {ahead.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-muted-foreground">{T.upcoming}</h3>
          <ul className="flex flex-col gap-1">
            {ahead.map((e) => (
              <OccurrenceRow key={e.id} event={e} tz={tz} noteId={noteByEvent.get(e.id)} />
            ))}
          </ul>
        </section>
      )}
      {past.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-muted-foreground">{T.past}</h3>
          <ul className="flex flex-col gap-1">
            {past.map((e) => (
              <OccurrenceRow key={e.id} event={e} tz={tz} noteId={noteByEvent.get(e.id)} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
