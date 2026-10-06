import { zodResolver } from '@hookform/resolvers/zod'
import { Trash2Icon } from 'lucide-react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { addDaysIso, isoWeekday, WEEKDAYS_SHORT, wallToUtc } from '@/lib/time'

import { rruleToWeekdays, weekdaysToRrule } from './rrule'
import {
  type RecurringEvent,
  useCreateEvent,
  useCreateRecurring,
  useDeleteRecurring,
  useUpdateRecurring,
} from './useCalendar'

const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'ЧЧ:ММ')

const schema = z
  .object({
    kind: z.enum(['personal', 'rest']),
    title: z.string().trim().min(1, 'Как назвать?').max(300),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Укажите дату'),
    start: time,
    end: time,
    repeat: z.array(z.string()),
    until: z.string(),
    location: z.string().trim().max(200),
    color: z.string().nullable(),
    note: z.string(),
  })
  .refine((v) => v.end !== v.start, { message: 'Конец совпадает с началом', path: ['end'] })
  .refine((v) => v.repeat.length > 0 || v.end > v.start, {
    message: 'Конец раньше начала',
    path: ['end'],
  })
  .refine((v) => !v.until || v.until >= v.date, { message: '«До» раньше начала', path: ['until'] })

type FormValues = z.infer<typeof schema>

export type PersonalDraft = { date: string; start?: string; end?: string; repeat?: number[] }

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  draft?: PersonalDraft
  /** Правка серии повтора. */
  recurring?: RecurringEvent
}

function plusHour(t: string): string {
  const [h, m] = t.split(':').map(Number)
  return `${String(Math.min(h + 1, 23)).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function toForm(draft?: PersonalDraft, rec?: RecurringEvent): FormValues {
  if (rec) {
    return {
      kind: rec.kind === 'rest' ? 'rest' : 'personal',
      title: rec.title,
      date: rec.start_date,
      start: rec.start_time,
      end: rec.end_time,
      repeat: (rruleToWeekdays(rec.rrule) ?? []).map(String),
      until: rec.until ?? '',
      location: rec.location ?? '',
      color: rec.color,
      note: rec.note,
    }
  }
  const start = draft?.start ?? '19:00'
  return {
    kind: 'personal',
    title: '',
    date: draft?.date ?? '',
    start,
    end: draft?.end ?? plusHour(start),
    repeat: (draft?.repeat ?? []).map(String),
    until: '',
    location: '',
    color: null,
    note: '',
  }
}

export function PersonalEventDialog({ open, onOpenChange, draft, recurring }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{recurring ? 'Повторяющееся событие' : 'Новое событие'}</DialogTitle>
        </DialogHeader>
        {open && (
          <PersonalEventForm
            key={recurring?.id ?? 'new'}
            draft={draft}
            recurring={recurring}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function PersonalEventForm({
  draft,
  recurring,
  onDone,
}: {
  draft?: PersonalDraft
  recurring?: RecurringEvent
  onDone: () => void
}) {
  const tz = useTimeZone()
  const createEvent = useCreateEvent()
  const createRecurring = useCreateRecurring()
  const updateRecurring = useUpdateRecurring()
  const deleteRecurring = useDeleteRecurring()
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: toForm(draft, recurring) })
  const { register, control, formState } = form
  const { errors } = formState
  const repeat = useWatch({ control, name: 'repeat' })
  const date = useWatch({ control, name: 'date' })
  const saving = createEvent.isPending || createRecurring.isPending || updateRecurring.isPending

  const onSubmit = form.handleSubmit(async (v) => {
    const common = {
      kind: v.kind,
      title: v.title,
      location: v.location || null,
      color: v.color,
      note: v.note,
    }
    try {
      if (v.repeat.length > 0 || recurring) {
        const body = {
          ...common,
          rrule: v.repeat.length ? weekdaysToRrule(v.repeat.map(Number)) : (recurring?.rrule ?? ''),
          start_date: v.date,
          until: v.until || null,
          start_time: v.start,
          end_time: v.end,
        }
        if (recurring) await updateRecurring.mutateAsync({ id: recurring.id, body })
        else await createRecurring.mutateAsync(body)
      } else {
        // Конец раньше начала невозможен (проверено схемой) -> тот же день
        await createEvent.mutateAsync({
          ...common,
          start: wallToUtc(v.date, v.start, tz),
          end: wallToUtc(v.end > v.start ? v.date : addDaysIso(v.date, 1), v.end, tz),
        })
      }
      onDone()
    } catch {
      // тост уже показан
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <FieldGroup>
        <Controller
          control={control}
          name="kind"
          render={({ field }) => (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={field.value}
              onValueChange={(v) => v && field.onChange(v)}
            >
              <ToggleGroupItem value="personal">Личное</ToggleGroupItem>
              <ToggleGroupItem value="rest">Отдых</ToggleGroupItem>
            </ToggleGroup>
          )}
        />
        <Field data-invalid={!!errors.title}>
          <FieldLabel htmlFor="pe-title">Что</FieldLabel>
          <Input id="pe-title" autoFocus={!recurring} placeholder="Бассейн, врач, встреча…" {...register('title')} />
          {errors.title && <FieldError>{errors.title.message}</FieldError>}
        </Field>
        <div className="grid grid-cols-[1fr_auto_auto] items-end gap-2">
          <Field data-invalid={!!errors.date}>
            <FieldLabel htmlFor="pe-date">{repeat.length ? 'Начиная с' : 'Когда'}</FieldLabel>
            <Input id="pe-date" type="date" {...register('date')} />
          </Field>
          <Input type="time" step={300} aria-label="Начало" className="w-24" {...register('start')} />
          <Input type="time" step={300} aria-label="Конец" className="w-24" {...register('end')} />
        </div>
        {(errors.end || errors.date) && <FieldError>{errors.end?.message ?? errors.date?.message}</FieldError>}

        <Field>
          <FieldLabel>Повтор</FieldLabel>
          <Controller
            control={control}
            name="repeat"
            render={({ field }) => (
              <ToggleGroup
                type="multiple"
                variant="outline"
                size="sm"
                className="w-full"
                value={field.value}
                onValueChange={field.onChange}
              >
                {WEEKDAYS_SHORT.map((d, i) => (
                  <ToggleGroupItem key={d} value={String(i + 1)} className="flex-1">
                    {d}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
          <FieldDescription>
            {repeat.length
              ? 'Повторяется в выбранные дни.'
              : `Не повторяется. Нажмите дни, чтобы повторять${date ? ` (например, ${WEEKDAYS_SHORT[isoWeekday(date) - 1]})` : ''}.`}
          </FieldDescription>
        </Field>
        {repeat.length > 0 && (
          <Field data-invalid={!!errors.until}>
            <FieldLabel htmlFor="pe-until">До (необязательно)</FieldLabel>
            <Input id="pe-until" type="date" min={date} {...register('until')} />
            {errors.until && <FieldError>{errors.until.message}</FieldError>}
          </Field>
        )}

        <Field>
          <FieldLabel htmlFor="pe-location">Где</FieldLabel>
          <Input id="pe-location" {...register('location')} />
        </Field>
        <Field>
          <FieldLabel>Цвет</FieldLabel>
          <Controller
            control={control}
            name="color"
            render={({ field }) => <ColorPicker value={field.value} onChange={field.onChange} />}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="pe-note">Заметка</FieldLabel>
          <Textarea id="pe-note" rows={2} {...register('note')} />
        </Field>
      </FieldGroup>

      <DialogFooter className="flex-row items-center">
        {recurring && (
          <ConfirmButton
            title="Удалить всю серию?"
            description="Будущие повторы исчезнут из календаря. Прошедшие останутся."
            onConfirm={() => deleteRecurring.mutate(recurring.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить серию" className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" disabled={saving} className="ml-auto">
          {saving ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </DialogFooter>
    </form>
  )
}
