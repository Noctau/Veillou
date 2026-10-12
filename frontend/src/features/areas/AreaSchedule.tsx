import { parseISO } from 'date-fns'
import { CheckIcon, MapPinIcon } from 'lucide-react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { timeRange, useEventView } from '@/features/calendar/eventUtils'
import { type CalendarEvent, useCalendar } from '@/features/calendar/useCalendar'
import { NoteForEventButton } from '@/features/notes/NoteForEventButton'
import { useNotes } from '@/features/notes/useNotes'
import { describePattern } from '@/features/schedule/pattern'
import { useCurrentPeriod } from '@/features/schedule/useCurrentPeriod'
import { groupGrids, type ScheduleRule, slotsFor, useScheduleRules, useSlotGrids } from '@/features/schedule/useSchedule'
import { useNow } from '@/features/today/useNow'
import { AREAS_UI as T } from '@/lib/terms'
import { addDaysIso, dayStartUtc, formatDay, wallDate } from '@/lib/time'
import { cn } from '@/lib/utils'

import { renderFields } from './fields'
import type { Area } from './useAreas'

const PAST_DAYS = 21
const AHEAD_DAYS = 14
const PAST_SHOWN = 6
const AHEAD_SHOWN = 3

function RulesList({ area }: { area: Area }) {
  const { data: rules, isPending } = useScheduleRules({ area_id: area.id })
  const { data: gridRows = [] } = useSlotGrids()
  const view = useEventView()
  const grids = groupGrids(gridRows)

  const time = (r: ScheduleRule) => {
    if (r.start_time && r.end_time) return `${r.start_time}–${r.end_time}`
    const weekday = r.pattern.kind === 'weekly' ? r.pattern.weekdays[0] : 1
    const slot = slotsFor(grids.find((g) => g.id === r.slot_grid_id), weekday).find((s) => s.number === r.slot_from)
    return slot ? `${slot.start}–${slot.end}` : ''
  }

  if (isPending) return <Skeleton className="h-16" />
  if (!rules?.length) {
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
      {rules.map((r) => {
        const type = view.types.get(r.event_type_id)
        const fields = type ? renderFields(type.fields, r.fields, { onlyReminder: true }).map((f) => f.text) : []
        return (
          <li key={r.id} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{describePattern(r.pattern)}</span>
            {r.slot_from && <span>{T.slot(r.slot_from)}</span>}
            <span className="text-muted-foreground tabular-nums">{time(r)}</span>
            <span className="text-muted-foreground">{[type?.name, ...fields, r.location].filter(Boolean).join(' · ')}</span>
          </li>
        )
      })}
    </ul>
  )
}

function OccurrenceRow({ event, tz, noteId }: { event: CalendarEvent; tz: string; noteId?: string }) {
  const view = useEventView()
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
          <span>{cancelled ? T.cancelled : view.details(event, { withPlace: false })}</span>
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
  const { today, tz } = useCurrentPeriod()
  const from = dayStartUtc(addDaysIso(today, -PAST_DAYS), tz)
  const to = dayStartUtc(addDaysIso(today, AHEAD_DAYS + 1), tz)
  const { data, isPending } = useCalendar(from, to)
  const { data: notes } = useNotes({ area_id: area.id })
  const noteByEvent = new Map(notes?.filter((n) => n.event_id).map((n) => [n.event_id!, n.id]))

  const now = useNow()
  // Жёсткие события сферы (вхождения её правил и разовые)
  const occurrences = (data?.events ?? []).filter((e) => e.kind === 'busy' && e.area_id === area.id)
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
