import { zodResolver } from '@hookform/resolvers/zod'
import {
  BanIcon,
  CheckIcon,
  ClipboardCheckIcon,
  ExternalLinkIcon,
  PencilIcon,
  PinOffIcon,
  RepeatIcon,
  RotateCcwIcon,
  Trash2Icon,
  Undo2Icon,
  XIcon,
} from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NoteForEventButton } from '@/features/notes/NoteForEventButton'
import { useAskFeel } from '@/features/plan/useAskFeel'
import { usePreviewPlan } from '@/features/plan/usePlan'
import { api } from '@/lib/api'
import { paletteColor } from '@/lib/colors'
import { FieldValuesView } from '@/features/areas/FieldValuesView'
import { ScheduleRuleDialog } from '@/features/schedule/ScheduleRuleDialog'
import { useScheduleRules } from '@/features/schedule/useSchedule'
import { PrepPanel } from '@/features/prep/PrepPanel'
import { EVENT_UI as E, KIND_SINGLE, PREP_UI } from '@/lib/terms'
import { addDaysIso, formatDay, wallDate, wallTime, wallToUtc } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'
import { cn } from '@/lib/utils'

import { placeOf, useEventView } from './eventUtils'
import {
  type CalendarEvent,
  type EventUpdate,
  useDeleteEvent,
  useResetEvent,
  useUpdateEvent,
} from './useCalendar'

const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'ЧЧ:ММ')
const schema = z
  .object({
    title: z.string().trim().min(1, 'Название').max(300),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Дата'),
    start: time,
    end: time,
    location: z.string().trim().max(200),
  })
  .refine((v) => v.end !== v.start, { message: 'Конец совпадает с началом', path: ['end'] })
type FormValues = z.infer<typeof schema>

type Props = {
  event: CalendarEvent | null
  onOpenChange: (open: boolean) => void
}

/** Карточка события: детали, поля типа и действия (отменить / перенести / место). */
export function EventDetailsDialog({ event, onOpenChange }: Props) {
  const [seriesId, setSeriesId] = useState<string | null>(null)
  const { data: rules = [] } = useScheduleRules({}, !!seriesId)
  const series = rules.find((r) => r.id === seriesId)

  return (
    <>
      <Dialog open={!!event} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          {event && (
            <EventDetails
              key={event.id}
              event={event}
              onClose={() => onOpenChange(false)}
              onEditSeries={(id) => {
                onOpenChange(false)
                setSeriesId(id)
              }}
            />
          )}
        </DialogContent>
      </Dialog>
      <ScheduleRuleDialog
        open={!!series}
        onOpenChange={(open) => !open && setSeriesId(null)}
        periodId={series?.period_id ?? null}
        rule={series}
      />
    </>
  )
}

/** Блок подзадачи → экран её задания. */
function OpenTaskButton({ subtaskId }: { subtaskId: string }) {
  const navigate = useNavigate()
  const open = async () => {
    const { data } = await api.GET('/api/v1/subtasks/{subtask_id}', { params: { path: { subtask_id: subtaskId } } })
    if (data) navigate(`/tasks/${data.task_id}`)
  }
  return (
    <Button variant="ghost" onClick={() => void open()}>
      <ExternalLinkIcon /> Задание
    </Button>
  )
}

function EventDetails({
  event,
  onClose,
  onEditSeries,
}: {
  event: CalendarEvent
  onClose: () => void
  onEditSeries: (id: string) => void
}) {
  const tz = useTimeZone()
  const update = useUpdateEvent()
  const remove = useDeleteEvent()
  const reset = useResetEvent()
  const preview = usePreviewPlan()
  const askFeel = useAskFeel()
  const [editing, setEditing] = useState(false)
  const [prepOpen, setPrepOpen] = useState(false)

  const view = useEventView()
  const type = view.typeOf(event)
  const isDoable = view.isDoable(event)
  // Вхождение правила со сферой: название — от сферы, правится место и время
  const isClass = event.kind === 'busy' && !!event.template_id && !!event.area_id
  // Событие типа с подготовкой: план подготовки — прямо из карточки (M20.2)
  const fromTemplate = !!event.template_id
  const cancelled = event.status === 'cancelled'
  const canPrep = event.kind === 'busy' && !!type?.supports_prep && !cancelled
  const done = event.status === 'done'
  const missed = event.status === 'missed'
  // Гибкий блок (подзадача и т. п.): его двигает планировщик
  const flexible = !event.is_fixed
  const day = wallDate(event.start, tz)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: event.title,
      date: day,
      start: wallTime(event.start, tz),
      end: wallTime(event.end, tz),
      location: event.location ?? '',
    },
  })
  const { errors } = form.formState

  const patch = (body: EventUpdate) => update.mutate({ id: event.id, body }, { onSuccess: onClose })

  const markDone = () =>
    update.mutate(
      { id: event.id, body: { status: 'done' } },
      {
        onSuccess: () => {
          onClose()
          if (event.source_type === 'subtask' && event.source_id) askFeel(event.source_id)
        },
      },
    )

  // «Не сделано» — блок уходит в историю, а подзадача сразу получает новое место в превью
  const markMissed = () =>
    update.mutate(
      { id: event.id, body: { status: 'missed' } },
      {
        onSuccess: () => {
          onClose()
          preview.mutate({ reason: 'missed', quiet: true })
        },
      },
    )

  const onSave = form.handleSubmit((v) => {
    const endDay = v.end > v.start ? v.date : addDaysIso(v.date, 1)
    patch({
      ...(isClass ? {} : { title: v.title }),
      start: wallToUtc(v.date, v.start, tz),
      end: wallToUtc(endDay, v.end, tz),
      location: v.location || null,
    })
  })

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <span className={cn('size-3 shrink-0 rounded-full', paletteColor(view.color(event)).bg)} />
          <span className={cn(cancelled && 'line-through')}>{event.title}</span>
        </DialogTitle>
        <DialogDescription>
          {formatDay(day, { weekday: 'long', month: 'long' })}, {wallTime(event.start, tz)}–{wallTime(event.end, tz)}
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2 text-sm">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary">{type?.name ?? KIND_SINGLE[event.kind]}</Badge>
          {event.slot && <Badge variant="outline">{E.slot(event.slot)}</Badge>}
          {cancelled && <Badge variant="destructive">{E.cancelled}</Badge>}
          {done && <Badge variant="outline">{E.done}</Badge>}
          {missed && <Badge variant="destructive">{E.missed}</Badge>}
          {flexible && event.is_pinned && <Badge variant="outline">{E.pinned}</Badge>}
          {event.detached && !cancelled && <Badge variant="outline">{E.detached}</Badge>}
        </div>
        {placeOf(event, type) && <p>{placeOf(event, type)}</p>}
        {type && <FieldValuesView defs={type.fields} values={event.fields} />}
        {event.note && <p className="whitespace-pre-wrap text-muted-foreground">{event.note}</p>}
      </div>

      {editing ? (
        <form onSubmit={onSave} noValidate className="flex flex-col gap-4">
          <FieldGroup>
            {!isClass && (
              <Field data-invalid={!!errors.title}>
                <FieldLabel htmlFor="ev-title">Название</FieldLabel>
                <Input id="ev-title" {...form.register('title')} />
              </Field>
            )}
            <div className="grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_auto_auto]">
              <Field className="col-span-2 sm:col-span-1">
                <FieldLabel htmlFor="ev-date">{isClass ? 'Перенести на' : 'Когда'}</FieldLabel>
                <Input id="ev-date" type="date" {...form.register('date')} />
              </Field>
              <Input type="time" step={300} aria-label="Начало" className="sm:w-24" {...form.register('start')} />
              <Input type="time" step={300} aria-label="Конец" className="sm:w-24" {...form.register('end')} />
            </div>
            {errors.end && <FieldError>{errors.end.message}</FieldError>}
            <Field>
              <FieldLabel htmlFor="ev-location">{type?.location_label || 'Где'}</FieldLabel>
              <Input id="ev-location" {...form.register('location')} />
            </Field>
          </FieldGroup>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Отмена
            </Button>
            <Button type="submit" disabled={update.isPending}>
              Сохранить
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-2">
          {isDoable && !done && (
            <Button onClick={markDone}>
              <CheckIcon /> Сделано
            </Button>
          )}
          {isDoable && flexible && event.status === 'planned' && (
            <Button variant="outline" onClick={markMissed}>
              <XIcon /> Не сделано
            </Button>
          )}
          {isDoable && (done || missed) && (
            <Button variant="outline" onClick={() => patch({ status: 'planned' })}>
              <Undo2Icon /> Снять отметку
            </Button>
          )}
          {flexible && event.is_pinned && event.status === 'planned' && (
            <Button variant="ghost" onClick={() => patch({ is_pinned: false })}>
              <PinOffIcon /> Открепить
            </Button>
          )}
          {!cancelled && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <PencilIcon /> {fromTemplate ? E.move : E.edit}
            </Button>
          )}
          {fromTemplate && !cancelled && (
            <Button variant="outline" onClick={() => remove.mutate(event.id, { onSuccess: onClose })}>
              <BanIcon /> {E.skip}
            </Button>
          )}
          {fromTemplate && event.detached && (
            <Button variant="ghost" onClick={() => reset.mutate(event.id, { onSuccess: onClose })}>
              <RotateCcwIcon /> {E.asScheduled}
            </Button>
          )}
          {event.template_type === 'schedule_rule' && event.template_id && (
            <Button variant="ghost" onClick={() => onEditSeries(event.template_id!)}>
              <RepeatIcon /> {E.series}
            </Button>
          )}
          {event.source_type === 'subtask' && event.source_id && (
            <OpenTaskButton subtaskId={event.source_id} />
          )}
          {canPrep && (
            <Button variant="ghost" onClick={() => setPrepOpen(true)}>
              <ClipboardCheckIcon /> {PREP_UI.add}
            </Button>
          )}
          {event.source_type === 'prep_session' && event.area_id && (
            <Button variant="ghost" asChild>
              <Link to={`/areas/${event.area_id}?tab=prep`}>
                <ExternalLinkIcon /> {PREP_UI.add}
              </Link>
            </Button>
          )}
          {event.source_type === 'backlog_item' && (
            <Button variant="ghost" asChild>
              <Link to="/inbox">
                <ExternalLinkIcon /> Ящик
              </Link>
            </Button>
          )}
          {event.source_type === 'project' && event.source_id && (
            <Button variant="ghost" asChild>
              <Link to={`/projects/${event.source_id}`}>
                <ExternalLinkIcon /> Проект
              </Link>
            </Button>
          )}
          {event.source_type === 'task' && event.source_id && (
            <Button variant="ghost" asChild>
              <Link to={`/tasks/${event.source_id}`}>
                <ExternalLinkIcon /> Задание
              </Link>
            </Button>
          )}
          {event.kind === 'busy' && !!event.area_id && !cancelled && <NoteForEventButton eventId={event.id} variant="ghost" size="default" onDone={onClose} />}
          {!fromTemplate && (
            <ConfirmButton title="Удалить событие?" onConfirm={() => remove.mutate(event.id, { onSuccess: onClose })}>
              <Button variant="ghost" className="text-destructive">
                <Trash2Icon /> Удалить
              </Button>
            </ConfirmButton>
          )}
        </div>
      )}
      <Dialog open={prepOpen} onOpenChange={setPrepOpen}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{PREP_UI.editTitle}</DialogTitle>
            <DialogDescription>{event.title}</DialogDescription>
          </DialogHeader>
          {prepOpen && <PrepPanel eventId={event.id} areaId={event.area_id ?? undefined} />}
        </DialogContent>
      </Dialog>
    </>
  )
}
