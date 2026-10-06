import { zodResolver } from '@hookform/resolvers/zod'
import { PlusIcon, Trash2Icon, XIcon } from 'lucide-react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { z } from 'zod'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { PALETTE } from '@/lib/colors'

import {
  CONTROL_FORM_LABEL,
  type ControlForm,
  type Subject,
  useCreateSubject,
  useDeleteSubject,
  useUpdateSubject,
} from './useSubjects'

const CONTROL_FORMS = Object.keys(CONTROL_FORM_LABEL) as ControlForm[]

const schema = z.object({
  name: z.string().trim().min(1, 'Введите название').max(200),
  short_name: z.string().trim().max(50),
  color: z.string(),
  control_form: z.enum(CONTROL_FORMS as [ControlForm, ...ControlForm[]]),
  teachers: z.array(
    z.object({
      name: z.string().trim().min(1, 'Имя'),
      role: z.string().trim().max(200),
      contact: z.string().trim().max(200),
    }),
  ),
  links: z.array(
    z.object({
      title: z.string().trim().max(200),
      url: z.url({ error: 'Ссылка вида https://…' }),
    }),
  ),
  synonyms: z.string(),
  notes: z.string(),
})

type FormValues = z.infer<typeof schema>

function toForm(subject?: Subject, colorIndex = 0): FormValues {
  return {
    name: subject?.name ?? '',
    short_name: subject?.short_name ?? '',
    color: subject?.color ?? PALETTE[colorIndex % PALETTE.length].hex,
    control_form: subject?.control_form ?? 'exam',
    teachers: subject?.teachers.map((t) => ({ name: t.name, role: t.role ?? '', contact: t.contact ?? '' })) ?? [],
    links: subject?.links.map((l) => ({ title: l.title ?? '', url: l.url })) ?? [],
    synonyms: subject?.synonyms.join(', ') ?? '',
    notes: subject?.notes ?? '',
  }
}

function fromForm(values: FormValues) {
  return {
    ...values,
    short_name: values.short_name || null,
    synonyms: values.synonyms
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  }
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  subject?: Subject
  semesterId?: string
  /** Для нового предмета — следующий цвет палитры, чтобы предметы различались. */
  colorIndex?: number
}

export function SubjectDialog({ open, onOpenChange, subject, semesterId, colorIndex }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{subject ? 'Предмет' : 'Новый предмет'}</DialogTitle>
        </DialogHeader>
        {open && (
          <SubjectForm
            subject={subject}
            semesterId={semesterId}
            colorIndex={colorIndex}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SubjectForm({
  subject,
  semesterId,
  colorIndex,
  onDone,
}: {
  subject?: Subject
  semesterId?: string
  colorIndex?: number
  onDone: () => void
}) {
  const create = useCreateSubject()
  const update = useUpdateSubject()
  const remove = useDeleteSubject()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: toForm(subject, colorIndex),
  })
  const { register, control, formState } = form
  const { errors } = formState
  const teachers = useFieldArray({ control, name: 'teachers' })
  const links = useFieldArray({ control, name: 'links' })
  const saving = create.isPending || update.isPending

  const onSubmit = form.handleSubmit((values) => {
    const body = fromForm(values)
    if (subject) {
      update.mutate({ id: subject.id, body }, { onSuccess: onDone })
    } else {
      create.mutate({ ...body, semester_id: semesterId ?? null }, { onSuccess: onDone })
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <FieldGroup>
        <Field data-invalid={!!errors.name}>
          <FieldLabel htmlFor="subject-name">Название</FieldLabel>
          <Input id="subject-name" autoFocus={!subject} aria-invalid={!!errors.name} {...register('name')} />
          {errors.name && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field>
            <FieldLabel htmlFor="subject-short">Коротко</FieldLabel>
            <Input id="subject-short" placeholder="клим" {...register('short_name')} />
          </Field>
          <Field>
            <FieldLabel htmlFor="subject-control">Контроль</FieldLabel>
            <Controller
              control={control}
              name="control_form"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="subject-control" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CONTROL_FORMS.map((f) => (
                      <SelectItem key={f} value={f}>
                        {CONTROL_FORM_LABEL[f]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
        </div>
        <Field>
          <FieldLabel>Цвет</FieldLabel>
          <Controller
            control={control}
            name="color"
            render={({ field }) => <ColorPicker value={field.value} onChange={field.onChange} />}
          />
        </Field>
      </FieldGroup>

      <FieldSet>
        <FieldLegend variant="label">Преподаватели</FieldLegend>
        {teachers.fields.map((item, i) => (
          <div key={item.id} className="flex flex-col gap-2 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Input
                placeholder="Фамилия И. О."
                aria-label="Имя преподавателя"
                aria-invalid={!!errors.teachers?.[i]?.name}
                {...register(`teachers.${i}.name`)}
              />
              <Button type="button" variant="ghost" size="icon" aria-label="Убрать" onClick={() => teachers.remove(i)}>
                <XIcon />
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="лектор / семинарист" aria-label="Роль" {...register(`teachers.${i}.role`)} />
              <Input placeholder="почта, телефон" aria-label="Контакт" {...register(`teachers.${i}.contact`)} />
            </div>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => teachers.append({ name: '', role: '', contact: '' })}
        >
          <PlusIcon /> Преподаватель
        </Button>
      </FieldSet>

      <FieldSet>
        <FieldLegend variant="label">Ссылки</FieldLegend>
        {links.fields.map((item, i) => (
          <div key={item.id} className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Input placeholder="Название" aria-label="Название ссылки" className="w-1/3" {...register(`links.${i}.title`)} />
              <Input
                placeholder="https://…"
                aria-label="Адрес"
                inputMode="url"
                aria-invalid={!!errors.links?.[i]?.url}
                {...register(`links.${i}.url`)}
              />
              <Button type="button" variant="ghost" size="icon" aria-label="Убрать" onClick={() => links.remove(i)}>
                <XIcon />
              </Button>
            </div>
            {errors.links?.[i]?.url && <FieldError>{errors.links[i].url.message}</FieldError>}
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => links.append({ title: '', url: '' })}
        >
          <PlusIcon /> Ссылка
        </Button>
      </FieldSet>

      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="subject-synonyms">Другие названия</FieldLabel>
          <Input id="subject-synonyms" placeholder="климат, климатуха" {...register('synonyms')} />
          <FieldDescription>Через запятую — чтобы узнавать предмет в быстром вводе.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="subject-notes">Заметки</FieldLabel>
          <Textarea id="subject-notes" rows={3} {...register('notes')} />
        </Field>
      </FieldGroup>

      <DialogFooter className="flex-row items-center">
        {subject && (
          <ConfirmButton
            title={`Удалить «${subject.name}»?`}
            description="Пары этого предмета исчезнут из расписания."
            onConfirm={() => remove.mutate(subject.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить предмет" className="mr-auto text-destructive">
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
