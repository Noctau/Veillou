import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

import { DEFAULT_BELLS, PARITY_LABEL } from './parity'
import { type Semester, type SemesterCreate, useCreateSemester, useUpdateSemester } from './useSchedule'

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Укажите дату')

const schema = z
  .object({
    name: z.string().trim().min(1, 'Введите название').max(100),
    start_date: isoDate,
    classes_end: isoDate,
    session_start: z.string(),
    session_end: z.string(),
    first_week_parity: z.enum(['odd', 'even']),
  })
  .refine((v) => v.classes_end >= v.start_date, {
    message: 'Конец занятий раньше начала',
    path: ['classes_end'],
  })
  .refine((v) => !v.session_start === !v.session_end, {
    message: 'Укажите и начало, и конец сессии',
    path: ['session_end'],
  })
  .refine((v) => !v.session_start || v.session_end >= v.session_start, {
    message: 'Конец сессии раньше начала',
    path: ['session_end'],
  })

type FormValues = z.infer<typeof schema>

/** Разумные даты по умолчанию: осенний или весенний семестр. */
function defaults(today: string): FormValues {
  const year = Number(today.slice(0, 4))
  const month = Number(today.slice(5, 7))
  if (month >= 7) {
    return {
      name: `Осень ${year}`,
      start_date: `${year}-09-01`,
      classes_end: `${year}-12-27`,
      session_start: `${year + 1}-01-09`,
      session_end: `${year + 1}-01-25`,
      first_week_parity: 'odd',
    }
  }
  return {
    name: `Весна ${year}`,
    start_date: `${year}-02-09`,
    classes_end: `${year}-05-31`,
    session_start: `${year}-06-01`,
    session_end: `${year}-06-30`,
    first_week_parity: 'odd',
  }
}

function toForm(s: Semester): FormValues {
  return {
    name: s.name,
    start_date: s.start_date,
    classes_end: s.classes_end,
    session_start: s.session_start ?? '',
    session_end: s.session_end ?? '',
    first_week_parity: s.first_week_parity,
  }
}

function toBody(v: FormValues): SemesterCreate {
  return { ...v, session_start: v.session_start || null, session_end: v.session_end || null }
}

type Props = {
  semester?: Semester
  today: string
  onDone?: (semester: Semester) => void
}

export function SemesterForm({ semester, today, onDone }: Props) {
  const create = useCreateSemester()
  const update = useUpdateSemester()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: semester ? toForm(semester) : defaults(today),
  })
  const { register, control, formState } = form
  const { errors, isDirty } = formState
  const saving = create.isPending || update.isPending

  const onSubmit = form.handleSubmit((values) => {
    const body = toBody(values)
    if (semester) {
      update.mutate({ id: semester.id, body }, { onSuccess: (s) => onDone?.(s) })
    } else {
      create.mutate(
        { semester: body, bells: [{ weekday: null, slots: DEFAULT_BELLS }] },
        { onSuccess: (s) => onDone?.(s) },
      )
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FieldGroup>
        <Field data-invalid={!!errors.name}>
          <FieldLabel htmlFor="sem-name">Название</FieldLabel>
          <Input id="sem-name" {...register('name')} />
          {errors.name && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field data-invalid={!!errors.start_date}>
            <FieldLabel htmlFor="sem-start">Начало занятий</FieldLabel>
            <Input id="sem-start" type="date" {...register('start_date')} />
          </Field>
          <Field data-invalid={!!errors.classes_end}>
            <FieldLabel htmlFor="sem-end">Конец занятий</FieldLabel>
            <Input id="sem-end" type="date" {...register('classes_end')} />
            {errors.classes_end && <FieldError>{errors.classes_end.message}</FieldError>}
          </Field>
          <Field>
            <FieldLabel htmlFor="sem-ss">Начало сессии</FieldLabel>
            <Input id="sem-ss" type="date" {...register('session_start')} />
          </Field>
          <Field data-invalid={!!errors.session_end}>
            <FieldLabel htmlFor="sem-se">Конец сессии</FieldLabel>
            <Input id="sem-se" type="date" {...register('session_end')} />
            {errors.session_end && <FieldError>{errors.session_end.message}</FieldError>}
          </Field>
        </div>
        <Field>
          <FieldLabel>Первая неделя</FieldLabel>
          <Controller
            control={control}
            name="first_week_parity"
            render={({ field }) => (
              <ToggleGroup
                type="single"
                variant="outline"
                value={field.value}
                onValueChange={(v) => v && field.onChange(v)}
              >
                <ToggleGroupItem value="odd">{PARITY_LABEL.odd}</ToggleGroupItem>
                <ToggleGroupItem value="even">{PARITY_LABEL.even}</ToggleGroupItem>
              </ToggleGroup>
            )}
          />
          <FieldDescription>Дальше недели чередуются. В сессию пар нет.</FieldDescription>
        </Field>
      </FieldGroup>
      <Button type="submit" className="self-end" disabled={saving || (!!semester && !isDirty)}>
        {saving ? 'Сохраняем…' : semester ? 'Сохранить' : 'Создать семестр'}
      </Button>
    </form>
  )
}
