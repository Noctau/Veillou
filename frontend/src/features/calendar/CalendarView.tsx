import type { DatesSetArg, EventClickArg, EventContentArg, EventDropArg, EventInput } from '@fullcalendar/core'
import ruLocale from '@fullcalendar/core/locales/ru'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin, { type DateClickArg, type EventResizeDoneArg } from '@fullcalendar/interaction'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import { fromZonedTime } from 'date-fns-tz'
import { ChevronLeftIcon, ChevronRightIcon, PinIcon } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useDayProfileDays } from '@/features/dayprofiles/useDayProfiles'
import { useNow } from '@/features/today/useNow'
import { KIND_LABEL, UNTYPED_LAYER } from '@/lib/terms'
import { addDaysIso, toWallIso } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'

import { EventDetailsDialog } from './EventDetailsDialog'
import { type EventDraft, EventDialog } from './EventDialog'
import { type EventView, useEventView } from './eventUtils'
import { type CalendarEvent, type EventKind, useCalendar, useUpdateEvent } from './useCalendar'

/*
 * FullCalendar работает в «настенном» времени пользователя: timeZone='UTC', а
 * события отдаём наивными строками в TZ пользователя. Так не нужен плагин
 * часовых поясов, а сетка всегда в TZ из настроек, а не браузера.
 */

type View = 'timeGridDay' | 'timeGridWeek' | 'dayGridMonth'
const VIEWS: { value: View; label: string }[] = [
  { value: 'timeGridDay', label: 'День' },
  { value: 'timeGridWeek', label: 'Неделя' },
  { value: 'dayGridMonth', label: 'Месяц' },
]
// Слои: типы занятости (`type:<id>`), жёсткие без типа и блоки плана по виду
const FLEX_LAYERS: EventKind[] = ['subtask', 'backlog', 'prep', 'project']
const UNTYPED = 'untyped'
const STORAGE_KEY = 'veillou.calendar'

type Prefs = { view?: View; hidden?: string[] }

function layerOf(e: CalendarEvent): string {
  if (e.kind !== 'busy') return e.kind
  return e.event_type_id ? `type:${e.event_type_id}` : UNTYPED
}

function loadPrefs(): Prefs {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Prefs
  } catch {
    return {}
  }
}

function savePrefs(prefs: Prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // приватный режим — без запоминания
  }
}

/** Дата из FullCalendar (UTC-«настенная») → момент в TZ пользователя. */
function fcToUtc(d: Date, tz: string): string {
  return fromZonedTime(d.toISOString().slice(0, 19), tz).toISOString()
}

function defaultView(): View {
  return window.matchMedia('(min-width: 768px)').matches ? 'timeGridWeek' : 'timeGridDay'
}

/** Гибкий запланированный блок можно перетащить — он закрепится (планировщик его больше не двигает). */
function isMovable(e: CalendarEvent): boolean {
  return !e.is_fixed && e.status === 'planned'
}

function EventContent({ arg, view }: { arg: EventContentArg; view: EventView }) {
  const event = arg.event.extendedProps.source as CalendarEvent | undefined
  if (!event) return null
  const details = view.details(event)
  return (
    <div className="flex h-full flex-col overflow-hidden px-1 py-0.5 text-xs leading-tight">
      <span className="flex items-center gap-1 truncate font-medium">
        {!event.is_fixed && event.is_pinned && <PinIcon aria-label="Закреплено" className="size-3 shrink-0" />}
        <span className="truncate">{arg.event.title}</span>
      </span>
      <span className="truncate opacity-80">
        {arg.timeText}
        {details && ` · ${details}`}
      </span>
    </div>
  )
}

export function CalendarView() {
  const tz = useTimeZone()
  const now = useNow(60_000)
  const calendarRef = useRef<FullCalendar>(null)
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
  const [range, setRange] = useState<{
    from: string
    to: string
    title: string
    firstDay: string
    lastDay: string
  } | null>(null)
  const [opened, setOpened] = useState<CalendarEvent | null>(null)
  const [draft, setDraft] = useState<EventDraft | null>(null)
  const eventView = useEventView()

  const view = prefs.view ?? defaultView()
  const hidden = useMemo(() => new Set(prefs.hidden ?? []), [prefs.hidden])
  const { data } = useCalendar(range?.from, range?.to)
  const { data: dayProfiles } = useDayProfileDays(range?.firstDay ?? '', range?.lastDay ?? '', !!range)
  const profileOf = useMemo(() => new Map((dayProfiles ?? []).map((d) => [d.date, d.name])), [dayProfiles])
  const update = useUpdateEvent()

  const updatePrefs = (next: Prefs) => {
    setPrefs(next)
    savePrefs(next)
  }

  const events = useMemo<EventInput[]>(() => {
    if (!data) return []
    const items: EventInput[] = data.events
      .filter((e) => !hidden.has(layerOf(e)))
      .map((e) => {
        const color = eventView.color(e)
        const muted = e.status === 'cancelled' || e.status === 'done' || e.status === 'missed'
        return {
          id: e.id,
          title: e.title,
          start: toWallIso(e.start, tz),
          end: toWallIso(e.end, tz),
          backgroundColor: color,
          borderColor: color,
          textColor: '#fff',
          editable: isMovable(e),
          classNames: [
            muted ? 'opacity-50' : '',
            e.status === 'cancelled' ? 'line-through' : '',
          ].filter(Boolean),
          extendedProps: { source: e },
        }
      })
    // Выходные — фоном на весь день
    for (const d of data.days_off) {
      items.push({
        id: `off-${d.id}`,
        title: d.title || 'Выходной',
        start: d.date_from,
        end: addDaysIso(d.date_to, 1),
        allDay: true,
        display: 'background',
        backgroundColor: '#64748b',
      })
    }
    return items
  }, [data, hidden, tz, eventView])

  // Типы занятости видны всегда, остальные слои — когда в них есть события (или скрыты)
  const present = new Set((data?.events ?? []).map(layerOf))
  const layers: { key: string; label: string }[] = [
    ...[...eventView.types.values()].map((t) => ({ key: `type:${t.id}`, label: t.name_plural })),
    ...(present.has(UNTYPED) || hidden.has(UNTYPED) ? [{ key: UNTYPED, label: UNTYPED_LAYER }] : []),
    ...FLEX_LAYERS.filter((k) => present.has(k) || hidden.has(k)).map((k) => ({ key: k, label: KIND_LABEL[k] })),
  ]

  const api = () => calendarRef.current?.getApi()

  const onDatesSet = (arg: DatesSetArg) =>
    setRange({
      from: fcToUtc(arg.start, tz),
      to: fcToUtc(arg.end, tz),
      title: arg.view.title,
      firstDay: arg.start.toISOString().slice(0, 10),
      lastDay: addDaysIso(arg.end.toISOString().slice(0, 10), -1),
    })

  const onEventClick = (arg: EventClickArg) => {
    const source = arg.event.extendedProps.source as CalendarEvent | undefined
    if (source) setOpened(source)
  }

  const onDateClick = (arg: DateClickArg) => {
    const iso = arg.date.toISOString()
    setDraft(arg.allDay ? { date: iso.slice(0, 10) } : { date: iso.slice(0, 10), start: iso.slice(11, 16) })
  }

  // Перетаскивание / растягивание гибкого блока: бэкенд ставит pin, план пересчитается
  const onEventMove = (arg: EventDropArg | EventResizeDoneArg) => {
    const { start, end } = arg.event
    if (!start || !end) return arg.revert()
    update.mutate(
      { id: arg.event.id, body: { start: fcToUtc(start, tz), end: fcToUtc(end, tz) } },
      { onError: () => arg.revert() },
    )
  }

  const changeView = (v: View) => {
    updatePrefs({ ...prefs, view: v })
    api()?.changeView(v)
  }

  const toggleLayers = (visible: string[]) =>
    updatePrefs({ ...prefs, hidden: layers.map((l) => l.key).filter((k) => !visible.includes(k)) })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center">
          <Button variant="ghost" size="icon" aria-label="Назад" onClick={() => api()?.prev()}>
            <ChevronLeftIcon />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Вперёд" onClick={() => api()?.next()}>
            <ChevronRightIcon />
          </Button>
          <Button variant="outline" size="sm" onClick={() => api()?.today()}>
            Сегодня
          </Button>
        </div>
        <span className="font-medium first-letter:uppercase">{range?.title}</span>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="ml-auto"
          value={view}
          onValueChange={(v) => v && changeView(v as View)}
        >
          {VIEWS.map((v) => (
            <ToggleGroupItem key={v.value} value={v.value}>
              {v.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <ToggleGroup
        type="multiple"
        size="sm"
        variant="outline"
        className="flex-wrap"
        aria-label="Слои"
        value={layers.map((l) => l.key).filter((k) => !hidden.has(k))}
        onValueChange={toggleLayers}
      >
        {layers.map((l) => (
          <ToggleGroupItem key={l.key} value={l.key}>
            {l.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <div className="text-sm [--fc-border-color:var(--border)] [--fc-neutral-bg-color:var(--muted)] [--fc-now-indicator-color:var(--destructive)] [--fc-page-bg-color:var(--background)] [--fc-today-bg-color:color-mix(in_oklch,var(--primary)_7%,transparent)] [&_.fc-col-header-cell-cushion]:font-medium [&_.fc-daygrid-day-number]:text-muted-foreground [&_.fc-event]:cursor-pointer [&_.fc-timegrid-slot]:h-10 [&_.fc-timegrid-slot-label]:text-xs [&_.fc-timegrid-slot-label]:text-muted-foreground">
        <FullCalendar
          ref={calendarRef}
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          locale={ruLocale}
          timeZone="UTC"
          now={toWallIso(now, tz)}
          initialView={view}
          headerToolbar={false}
          firstDay={1}
          height="auto"
          nowIndicator
          slotMinTime="07:00:00"
          slotMaxTime="24:00:00"
          slotDuration="00:30:00"
          allDayText=""
          dayMaxEvents={3}
          eventDisplay="block"
          eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
          slotLabelFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
          events={events}
          datesSet={onDatesSet}
          eventClick={onEventClick}
          dateClick={onDateClick}
          eventDrop={onEventMove}
          eventResize={onEventMove}
          snapDuration="00:15:00"
          eventLongPressDelay={400}
          dayHeaderContent={(arg) => {
            // Режим дня — под датой (в неделе и дне; в месяце заголовки — дни недели)
            const profile = arg.view.type.startsWith('timeGrid')
              ? profileOf.get(arg.date.toISOString().slice(0, 10))
              : undefined
            return (
              <div className="flex flex-col items-center leading-tight">
                <span>{arg.text}</span>
                {profile && <span className="text-[10px] font-normal text-muted-foreground">{profile}</span>}
              </div>
            )
          }}
          eventContent={(arg) => (arg.event.display === 'background' ? undefined : <EventContent arg={arg} view={eventView} />)}
        />
      </div>

      <EventDetailsDialog event={opened} onOpenChange={(open) => !open && setOpened(null)} />
      <EventDialog open={!!draft} onOpenChange={(open) => !open && setDraft(null)} draft={draft ?? undefined} />
    </div>
  )
}
