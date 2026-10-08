import { zodResolver } from '@hookform/resolvers/zod'
import { Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { intIn, wallTime as wallTimeSchema } from '@/features/settings/zod'
import { addDaysIso, todayIn, wallDate, wallTime, wallToUtc } from '@/lib/time'

import { type Exam, useCreateExam, useDeleteExam, useUpdateExam } from './useExams'

const schema = z.object({
  title: z.string().trim().max(300),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Укажите дату'),
  time: wallTimeSchema,
  duration_min: intIn(15, 600),
  location: z.string().trim().max(200),
  prep_days: intIn(1, 60),
  learn_min: intIn(5, 240),
  review_min: intIn(1, 120),
  run_min: intIn(1, 60),
})
type FormValues = z.infer<typeof schema>

type Props = {
  subjectId: string
  exam?: Exam
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Экзамен: дата, время, аудитория; подготовка — за сколько дней и минуты на вопрос. */
export function ExamDialog({ subjectId, exam, open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{exam ? 'Экзамен' : 'Новый экзамен'}</DialogTitle>
        </DialogHeader>
        {open && <ExamForm key={exam?.id ?? 'new'} subjectId={subjectId} exam={exam} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ExamForm({ subjectId, exam, onDone }: { subjectId: string; exam?: Exam; onDone: () => void }) {
  const tz = useTimeZone()
  const create = useCreateExam()
  const update = useUpdateExam()
  const remove = useDeleteExam()
  const [advanced, setAdvanced] = useState(false)
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: exam && !exam.title.startsWith('Экзамен') ? exam.title : '',
      date: exam ? wallDate(exam.starts_at, tz) : addDaysIso(todayIn(tz), 14),
      time: exam ? wallTime(exam.starts_at, tz) : '10:00',
      duration_min: exam?.duration_min ?? 180,
      location: exam?.location ?? '',
      prep_days: exam?.prep_days ?? 7,
      learn_min: exam?.learn_min ?? 45,
      review_min: exam?.review_min ?? 15,
      run_min: exam?.run_min ?? 5,
    },
  })
  const { errors } = form.formState
  const num = { valueAsNumber: true } as const

  const onSubmit = form.handleSubmit((v) => {
    const body = {
      title: v.title,
      starts_at: wallToUtc(v.date, v.time, tz),
      duration_min: v.duration_min,
      location: v.location || null,
      prep_days: v.prep_days,
      learn_min: v.learn_min,
      review_min: v.review_min,
      run_min: v.run_min,
    }
    if (exam) update.mutate({ id: exam.id, body }, { onSuccess: onDone })
    else create.mutate({ ...body, subject_id: subjectId, note: '' }, { onSuccess: onDone })
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <FieldGroup>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Field data-invalid={!!errors.date}>
            <FieldLabel htmlFor="ex-date">Дата</FieldLabel>
            <Input id="ex-date" type="date" {...form.register('date')} />
            {errors.date && <FieldError>{errors.date.message}</FieldError>}
          </Field>
          <Field data-invalid={!!errors.time}>
            <FieldLabel htmlFor="ex-time">Начало</FieldLabel>
            <Input id="ex-time" type="time" step={300} className="w-28" {...form.register('time')} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field>
            <FieldLabel htmlFor="ex-location">Аудитория</FieldLabel>
            <Input id="ex-location" {...form.register('location')} />
          </Field>
          <Field data-invalid={!!errors.duration_min}>
            <FieldLabel htmlFor="ex-duration">Длится, мин</FieldLabel>
            <Input id="ex-duration" type="number" inputMode="numeric" step={15} {...form.register('duration_min', num)} />
          </Field>
        </div>
        <Field data-invalid={!!errors.prep_days}>
          <FieldLabel htmlFor="ex-prep">Начать готовиться за, дней</FieldLabel>
          <Input id="ex-prep" type="number" inputMode="numeric" className="w-28" {...form.register('prep_days', num)} />
          {errors.prep_days && <FieldError>{errors.prep_days.message}</FieldError>}
        </Field>
        {advanced ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Field data-invalid={!!errors.learn_min}>
                <FieldLabel htmlFor="ex-learn">Выучить</FieldLabel>
                <Input id="ex-learn" type="number" inputMode="numeric" {...form.register('learn_min', num)} />
              </Field>
              <Field data-invalid={!!errors.review_min}>
                <FieldLabel htmlFor="ex-review">Повторить</FieldLabel>
                <Input id="ex-review" type="number" inputMode="numeric" {...form.register('review_min', num)} />
              </Field>
              <Field data-invalid={!!errors.run_min}>
                <FieldLabel htmlFor="ex-run">Прогон</FieldLabel>
                <Input id="ex-run" type="number" inputMode="numeric" {...form.register('run_min', num)} />
              </Field>
            </div>
            <FieldDescription>Минут на один вопрос. Повторения — через 1, 3 и 7 дней, накануне — общий прогон.</FieldDescription>
          </>
        ) : (
          <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setAdvanced(true)}>
            Время на вопрос: {exam?.learn_min ?? 45} / {exam?.review_min ?? 15} / {exam?.run_min ?? 5} мин
          </Button>
        )}
        <Field>
          <FieldLabel htmlFor="ex-title">Название</FieldLabel>
          <Input id="ex-title" placeholder="Экзамен: <предмет>" {...form.register('title')} />
        </Field>
      </FieldGroup>
      <DialogFooter className="flex-row items-center">
        {exam && (
          <ConfirmButton
            title="Удалить экзамен?"
            description="Вопросы и план подготовки тоже удалятся."
            onConfirm={() => remove.mutate(exam.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить" className="mr-auto text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" disabled={create.isPending || update.isPending}>
          Сохранить
        </Button>
      </DialogFooter>
    </form>
  )
}
