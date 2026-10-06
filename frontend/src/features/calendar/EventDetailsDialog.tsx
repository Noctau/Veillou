import { zodResolver } from '@hookform/resolvers/zod'
import { BanIcon, CheckIcon, ExternalLinkIcon, PencilIcon, RepeatIcon, RotateCcwIcon, Trash2Icon, Undo2Icon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { z } from 'zod'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NoteForEventButton } from '@/features/notes/NoteForEventButton'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { api } from '@/lib/api'
import { paletteColor } from '@/lib/colors'
import { addDaysIso, formatDay, wallDate, wallTime, wallToUtc } from '@/lib/time'
import { cn } from '@/lib/utils'

import { classDetails, eventColor, isDoable, KIND_SINGLE } from './eventUtils'
import { PersonalEventDialog } from './PersonalEventDialog'
import {
  type CalendarEvent,
  type EventUpdate,
  useDeleteEvent,
  useRecurringEvents,
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

/** Карточка события: детали и действия. Для пары — отменить / перенести / аудитория. */
export function EventDetailsDialog({ event, onOpenChange }: Props) {
  const [seriesId, setSeriesId] = useState<string | null>(null)
  const { data: recurring = [] } = useRecurringEvents()
  const series = recurring.find((r) => r.id === seriesId)

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
      <PersonalEventDialog
        open={!!series}
        onOpenChange={(open) => !open && setSeriesId(null)}
        recurring={series}
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
  const [editing, setEditing] = useState(false)

  const isClass = event.kind === 'class'
  const fromTemplate = !!event.template_id
  const cancelled = event.status === 'cancelled'
  const done = event.status === 'done'
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
          <span className={cn('size-3 shrink-0 rounded-full', paletteColor(eventColor(event)).bg)} />
          <span className={cn(cancelled && 'line-through')}>{event.title}</span>
        </DialogTitle>
        <DialogDescription>
          {formatDay(day, { weekday: 'long', month: 'long' })}, {wallTime(event.start, tz)}–{wallTime(event.end, tz)}
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2 text-sm">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary">{KIND_SINGLE[event.kind]}</Badge>
          {event.pair_number && <Badge variant="outline">{event.pair_number} пара</Badge>}
          {cancelled && <Badge variant="destructive">Отменено</Badge>}
          {done && <Badge variant="outline">Сделано</Badge>}
          {event.detached && !cancelled && <Badge variant="outline">Изменено вручную</Badge>}
        </div>
        {isClass ? (
          classDetails(event) && <p>{classDetails(event)}</p>
        ) : (
          event.location && <p>{event.location}</p>
        )}
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
              <FieldLabel htmlFor="ev-location">{isClass ? 'Аудитория' : 'Где'}</FieldLabel>
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
          {isDoable(event) && (
            <Button onClick={() => patch({ status: done ? 'planned' : 'done' })}>
              {done ? <Undo2Icon /> : <CheckIcon />}
              {done ? 'Не сделано' : 'Сделано'}
            </Button>
          )}
          {!cancelled && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <PencilIcon /> {isClass ? 'Перенести / аудитория' : 'Изменить'}
            </Button>
          )}
          {fromTemplate && !cancelled && (
            <Button variant="outline" onClick={() => remove.mutate(event.id, { onSuccess: onClose })}>
              <BanIcon /> {isClass ? 'Отменить пару' : 'Пропустить'}
            </Button>
          )}
          {fromTemplate && event.detached && (
            <Button variant="ghost" onClick={() => reset.mutate(event.id, { onSuccess: onClose })}>
              <RotateCcwIcon /> Как в расписании
            </Button>
          )}
          {event.template_type === 'recurring' && event.template_id && (
            <Button variant="ghost" onClick={() => onEditSeries(event.template_id!)}>
              <RepeatIcon /> Вся серия
            </Button>
          )}
          {event.source_type === 'subtask' && event.source_id && (
            <OpenTaskButton subtaskId={event.source_id} />
          )}
          {isClass && !cancelled && <NoteForEventButton eventId={event.id} variant="ghost" size="default" onDone={onClose} />}
          {!fromTemplate && (
            <ConfirmButton title="Удалить событие?" onConfirm={() => remove.mutate(event.id, { onSuccess: onClose })}>
              <Button variant="ghost" className="text-destructive">
                <Trash2Icon /> Удалить
              </Button>
            </ConfirmButton>
          )}
        </div>
      )}
    </>
  )
}
