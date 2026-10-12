import { zodResolver } from '@hookform/resolvers/zod'
import { PlusIcon, XIcon } from 'lucide-react'
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { SCHEDULE_UI as T } from '@/lib/terms'

import { DEFAULT_SLOTS } from './cycle'
import { type Period, type PeriodCreate, useCreatePeriod, useUpdatePeriod } from './useSchedule'

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, T.required)

const schema = z
  .object({
    name: z.string().trim().min(1, T.required).max(100),
    start_date: isoDate,
    end_date: isoDate,
    cycle_weeks: z.number().int().min(1).max(8),
    first_cycle_week: z.number().int().min(1).max(8),
    pauses: z.array(z.object({ from: isoDate, to: isoDate, title: z.string().trim().max(200) })),
  })
  .refine((v) => v.end_date >= v.start_date, { message: 'Конец раньше начала', path: ['end_date'] })
  .refine((v) => v.first_cycle_week <= v.cycle_weeks, { message: 'Больше длины цикла', path: ['first_cycle_week'] })
  .refine((v) => v.pauses.every((p) => p.to >= p.from && p.from >= v.start_date && p.to <= v.end_date), {
    message: 'Пауза — внутри периода, конец не раньше начала',
    path: ['pauses'],
  })

type FormValues = z.infer<typeof schema>

/** Разумные даты по умолчанию: полгода с ближайшего 1-го числа. */
function defaults(today: string): FormValues {
  const year = Number(today.slice(0, 4))
  const month = Number(today.slice(5, 7))
  const autumn = month >= 7
  return {
    name: autumn ? `Осень ${year}` : `Весна ${year}`,
    start_date: autumn ? `${year}-09-01` : `${year}-02-09`,
    end_date: autumn ? `${year}-12-27` : `${year}-05-31`,
    cycle_weeks: 1,
    first_cycle_week: 1,
    pauses: [],
  }
}

function toForm(p: Period): FormValues {
  return {
    name: p.name,
    start_date: p.start_date,
    end_date: p.end_date,
    cycle_weeks: p.cycle_weeks,
    first_cycle_week: p.first_cycle_week,
    pauses: p.pauses.map((x) => ({ from: x.from, to: x.to, title: x.title })),
  }
}

type Props = {
  period?: Period
  today: string
  /** Новому периоду — сетка слотов по умолчанию (онбординг). */
  withDefaultSlots?: boolean
  onDone?: (period: Period) => void
}

export function PeriodForm({ period, today, withDefaultSlots = false, onDone }: Props) {
  const create = useCreatePeriod()
  const update = useUpdatePeriod()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: period ? toForm(period) : defaults(today),
  })
  const { register, control, formState } = form
  const { errors, isDirty } = formState
  const pauses = useFieldArray({ control, name: 'pauses' })
  const cycle = useWatch({ control, name: 'cycle_weeks' })
  const saving = create.isPending || update.isPending

  const onSubmit = form.handleSubmit((values) => {
    const body: PeriodCreate = values
    if (period) {
      update.mutate({ id: period.id, body }, { onSuccess: (p) => onDone?.(p) })
    } else {
      const slots = withDefaultSlots ? [{ weekday: null, slots: DEFAULT_SLOTS }] : undefined
      create.mutate({ period: body, slots }, { onSuccess: (p) => onDone?.(p) })
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FieldGroup>
        <Field data-invalid={!!errors.name}>
          <FieldLabel htmlFor="period-name">{T.name}</FieldLabel>
          <Input id="period-name" {...register('name')} />
          {errors.name && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field data-invalid={!!errors.start_date}>
            <FieldLabel htmlFor="period-start">{T.startDate}</FieldLabel>
            <Input id="period-start" type="date" {...register('start_date')} />
          </Field>
          <Field data-invalid={!!errors.end_date}>
            <FieldLabel htmlFor="period-end">{T.endDate}</FieldLabel>
            <Input id="period-end" type="date" {...register('end_date')} />
            {errors.end_date && <FieldError>{errors.end_date.message}</FieldError>}
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="period-cycle">{T.cycle}</FieldLabel>
          <Input
            id="period-cycle"
            type="number"
            min={1}
            max={8}
            className="w-20"
            {...register('cycle_weeks', { valueAsNumber: true })}
          />
          <FieldDescription>{T.cycleHint}</FieldDescription>
        </Field>
        {cycle > 1 && (
          <Field data-invalid={!!errors.first_cycle_week}>
            <FieldLabel>{T.firstWeek}</FieldLabel>
            <Controller
              control={control}
              name="first_cycle_week"
              render={({ field }) => (
                <ToggleGroup
                  type="single"
                  variant="outline"
                  className="justify-start"
                  value={String(field.value)}
                  onValueChange={(v) => v && field.onChange(Number(v))}
                >
                  {Array.from({ length: Math.min(cycle, 8) }, (_, i) => (
                    <ToggleGroupItem key={i} value={String(i + 1)} className="px-3">
                      {i + 1}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              )}
            />
            {errors.first_cycle_week && <FieldError>{errors.first_cycle_week.message}</FieldError>}
          </Field>
        )}
        <FieldSet>
          <FieldLegend variant="label">{T.pauses}</FieldLegend>
          <FieldDescription>{T.pausesHint}</FieldDescription>
          <ul className="flex flex-col gap-2">
            {pauses.fields.map((p, i) => (
              <li key={p.id} className="grid grid-cols-[1fr_1fr_2rem] items-center gap-2 sm:grid-cols-[8.5rem_8.5rem_1fr_2rem]">
                <Input type="date" aria-label={T.dayOffFrom} {...register(`pauses.${i}.from`)} />
                <Input type="date" aria-label={T.dayOffTo} {...register(`pauses.${i}.to`)} />
                <Input
                  placeholder={T.pauseTitle}
                  aria-label={T.name}
                  className="col-span-2 row-start-2 sm:col-span-1 sm:row-start-auto"
                  {...register(`pauses.${i}.title`)}
                />
                <Button type="button" variant="ghost" size="icon" aria-label={T.remove} onClick={() => pauses.remove(i)}>
                  <XIcon />
                </Button>
              </li>
            ))}
          </ul>
          {errors.pauses && <FieldError>{errors.pauses.message ?? errors.pauses.root?.message}</FieldError>}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => pauses.append({ from: form.getValues('end_date'), to: form.getValues('end_date'), title: '' })}
          >
            <PlusIcon /> {T.addPause}
          </Button>
        </FieldSet>
      </FieldGroup>
      <Button type="submit" className="self-end" disabled={saving || (!!period && !isDirty)}>
        {saving ? T.saving : period ? T.save : T.createPeriod}
      </Button>
    </form>
  )
}
