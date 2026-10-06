import { zodResolver } from '@hookform/resolvers/zod'
import { CopyIcon, SplitIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { type Subject, useCreateSubject } from '@/features/subjects/useSubjects'
import { PALETTE, paletteColor } from '@/lib/colors'
import { cn } from '@/lib/utils'
import { WEEKDAYS_FULL, WEEKDAYS_SHORT } from '@/lib/time'

import { CLASS_TYPE_LABEL, oppositeParity, RULE_PARITY_LABEL } from './parity'
import {
  type BellSlot,
  type ClassRule,
  type ClassRuleCreate,
  type ClassType,
  type Parity,
  type RuleParity,
  useCreateClassRule,
  useDeleteClassRule,
  useUpdateClassRule,
} from './useSchedule'

const NEW_SUBJECT = '__new__'
const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'ЧЧ:ММ')

const schema = z
  .object({
    subject_id: z.string().min(1, 'Выберите предмет'),
    new_subject: z.string().trim(),
    weekday: z.number().int().min(1).max(7),
    pair_number: z.number().int().nullable(),
    custom_time: z.boolean(),
    start_time: z.string(),
    end_time: z.string(),
    parity: z.enum(['all', 'odd', 'even']),
    class_type: z.enum(['lecture', 'seminar', 'lab', 'other']),
    location: z.string().trim().max(200),
    teacher: z.string().trim().max(200),
    valid_from: z.string(),
    valid_to: z.string(),
  })
  .refine((v) => v.subject_id !== NEW_SUBJECT || v.new_subject.length > 0, {
    message: 'Название предмета',
    path: ['new_subject'],
  })
  .refine((v) => (v.custom_time ? time.safeParse(v.start_time).success && time.safeParse(v.end_time).success : true), {
    message: 'Укажите время',
    path: ['end_time'],
  })
  .refine((v) => !v.custom_time || v.end_time > v.start_time, {
    message: 'Конец позже начала',
    path: ['end_time'],
  })
  .refine((v) => v.custom_time || v.pair_number !== null, { message: 'Выберите пару', path: ['pair_number'] })

type FormValues = z.infer<typeof schema>

export type RuleDraft = { weekday: number; pair_number: number | null; parity?: RuleParity }

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  semesterId: string
  subjects: Subject[]
  /** Звонки дня недели по номеру пары (для выбора пары). */
  bellsFor: (weekday: number) => BellSlot[]
  rule?: ClassRule
  draft?: RuleDraft
  /** Чётность, которая сейчас показана в сетке. */
  viewParity: Parity
  onEditRule: (rule: ClassRule) => void
}

export function ClassRuleDialog(props: Props) {
  const { open, onOpenChange, rule } = props
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{rule ? 'Пара' : 'Новая пара'}</DialogTitle>
        </DialogHeader>
        {open && <RuleForm key={rule?.id ?? 'new'} {...props} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function toForm(rule: ClassRule | undefined, draft: RuleDraft | undefined, subjects: Subject[]): FormValues {
  return {
    subject_id: rule?.subject_id ?? (subjects.length ? '' : NEW_SUBJECT),
    new_subject: '',
    weekday: rule?.weekday ?? draft?.weekday ?? 1,
    pair_number: rule ? rule.pair_number : (draft?.pair_number ?? null),
    custom_time: !!rule?.start_time,
    start_time: rule?.start_time ?? '',
    end_time: rule?.end_time ?? '',
    parity: rule?.parity ?? draft?.parity ?? 'all',
    class_type: rule?.class_type ?? 'lecture',
    location: rule?.location ?? '',
    teacher: rule?.teacher ?? '',
    valid_from: rule?.valid_from ?? '',
    valid_to: rule?.valid_to ?? '',
  }
}

function RuleForm({
  semesterId,
  subjects,
  bellsFor,
  rule,
  draft,
  viewParity,
  onEditRule,
  onDone,
}: Props & { onDone: () => void }) {
  const createRule = useCreateClassRule()
  const updateRule = useUpdateClassRule()
  const deleteRule = useDeleteClassRule()
  const createSubject = useCreateSubject()
  const [showValidity, setShowValidity] = useState(!!(rule?.valid_from || rule?.valid_to))

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: toForm(rule, draft, subjects),
  })
  const { register, control, formState } = form
  const { errors } = formState
  const weekday = useWatch({ control, name: 'weekday' })
  const customTime = useWatch({ control, name: 'custom_time' })
  const subjectId = useWatch({ control, name: 'subject_id' })
  const slots = bellsFor(weekday)
  const saving = createRule.isPending || updateRule.isPending || createSubject.isPending

  const body = (v: FormValues, subject_id: string): ClassRuleCreate => ({
    semester_id: semesterId,
    subject_id,
    weekday: v.weekday,
    pair_number: v.pair_number,
    start_time: v.custom_time ? v.start_time : null,
    end_time: v.custom_time ? v.end_time : null,
    parity: v.parity,
    class_type: v.class_type,
    location: v.location || null,
    teacher: v.teacher || null,
    valid_from: v.valid_from || null,
    valid_to: v.valid_to || null,
  })

  const onSubmit = form.handleSubmit(async (v) => {
    let subject_id = v.subject_id
    try {
      if (subject_id === NEW_SUBJECT) {
        const created = await createSubject.mutateAsync({
          name: v.new_subject,
          semester_id: semesterId,
          color: PALETTE[subjects.length % PALETTE.length].hex,
          control_form: 'exam',
          notes: '',
        })
        subject_id = created.id
      }
      const data = body(v, subject_id)
      if (rule) {
        const { semester_id: _, ...patch } = data
        await updateRule.mutateAsync({ id: rule.id, body: patch })
      } else {
        await createRule.mutateAsync(data)
      }
      onDone()
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  })

  const copyToDay = async (target: number) => {
    if (!rule) return
    const { id: _, ...rest } = rule
    await createRule.mutateAsync({ ...rest, weekday: target })
    toast.success(`Скопировано на ${WEEKDAYS_FULL[target - 1].toLowerCase()}`)
  }

  /** «Другая чётность»: копия с противоположной чётностью (у «каждой недели» — разделить). */
  const copyToOtherParity = async () => {
    if (!rule) return
    const { id: _, ...rest } = rule
    let mine: Parity
    if (rule.parity === 'all') {
      mine = viewParity
      await updateRule.mutateAsync({ id: rule.id, body: { parity: mine } })
    } else {
      mine = rule.parity
    }
    const copy = await createRule.mutateAsync({ ...rest, parity: oppositeParity(mine) })
    toast.success('Копия создана — поправьте её')
    onEditRule(copy)
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <FieldGroup>
        <Field data-invalid={!!errors.subject_id}>
          <FieldLabel htmlFor="rule-subject">Предмет</FieldLabel>
          <Controller
            control={control}
            name="subject_id"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="rule-subject" className="w-full">
                  <SelectValue placeholder="Выберите предмет" />
                </SelectTrigger>
                <SelectContent
                  onCloseAutoFocus={(e) => {
                    // «Новый предмет» -> сразу в поле названия, а не обратно на селект
                    if (form.getValues('subject_id') === NEW_SUBJECT) {
                      e.preventDefault()
                      form.setFocus('new_subject')
                    }
                  }}
                >
                  {subjects.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      <span className={cn('size-2.5 rounded-full', paletteColor(s.color).bg)} />
                      {s.name}
                    </SelectItem>
                  ))}
                  <SelectItem value={NEW_SUBJECT}>＋ Новый предмет</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
          {errors.subject_id && <FieldError>{errors.subject_id.message}</FieldError>}
        </Field>
        {subjectId === NEW_SUBJECT && (
          <Field data-invalid={!!errors.new_subject}>
            <Input
              placeholder="Название нового предмета"
              aria-label="Название нового предмета"
              {...register('new_subject')}
            />
            {errors.new_subject && <FieldError>{errors.new_subject.message}</FieldError>}
          </Field>
        )}

        <Controller
          control={control}
          name="class_type"
          render={({ field }) => (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              aria-label="Тип занятия"
              value={field.value}
              onValueChange={(v) => v && field.onChange(v as ClassType)}
            >
              {(Object.keys(CLASS_TYPE_LABEL) as ClassType[]).map((t) => (
                <ToggleGroupItem key={t} value={t}>
                  {CLASS_TYPE_LABEL[t]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        />

        <Controller
          control={control}
          name="parity"
          render={({ field }) => (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              aria-label="Чётность"
              value={field.value}
              onValueChange={(v) => v && field.onChange(v as RuleParity)}
            >
              {(Object.keys(RULE_PARITY_LABEL) as RuleParity[]).map((p) => (
                <ToggleGroupItem key={p} value={p}>
                  {RULE_PARITY_LABEL[p]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        />

        <div className="grid grid-cols-2 gap-4">
          <Field>
            <FieldLabel htmlFor="rule-weekday">День</FieldLabel>
            <Controller
              control={control}
              name="weekday"
              render={({ field }) => (
                <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger id="rule-weekday" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WEEKDAYS_FULL.map((d, i) => (
                      <SelectItem key={d} value={String(i + 1)}>
                        {d}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
          {!customTime && (
            <Field data-invalid={!!errors.pair_number}>
              <FieldLabel htmlFor="rule-pair">Пара</FieldLabel>
              <Controller
                control={control}
                name="pair_number"
                render={({ field }) => (
                  <Select
                    value={field.value === null ? '' : String(field.value)}
                    onValueChange={(v) => field.onChange(Number(v))}
                  >
                    <SelectTrigger id="rule-pair" className="w-full">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      {slots.map((s) => (
                        <SelectItem key={s.number} value={String(s.number)}>
                          {s.number} · {s.start}–{s.end}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {errors.pair_number && <FieldError>{errors.pair_number.message}</FieldError>}
            </Field>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Controller
            control={control}
            name="custom_time"
            render={({ field }) => (
              <Checkbox id="rule-custom" checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} />
            )}
          />
          <Label htmlFor="rule-custom">Своё время, не по звонкам</Label>
        </div>
        {customTime && (
          <Field data-invalid={!!errors.end_time}>
            <div className="flex items-center gap-2">
              <Input type="time" step={300} aria-label="Начало" {...register('start_time')} />
              <span className="text-muted-foreground">—</span>
              <Input type="time" step={300} aria-label="Конец" {...register('end_time')} />
            </div>
            {errors.end_time && <FieldError>{errors.end_time.message}</FieldError>}
          </Field>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Field>
            <FieldLabel htmlFor="rule-location">Аудитория</FieldLabel>
            <Input id="rule-location" placeholder="1801" {...register('location')} />
          </Field>
          <Field>
            <FieldLabel htmlFor="rule-teacher">Преподаватель</FieldLabel>
            <Input id="rule-teacher" {...register('teacher')} />
          </Field>
        </div>

        {showValidity ? (
          <div className="grid grid-cols-2 gap-4">
            <Field>
              <FieldLabel htmlFor="rule-from">Действует с</FieldLabel>
              <Input id="rule-from" type="date" {...register('valid_from')} />
            </Field>
            <Field>
              <FieldLabel htmlFor="rule-to">по</FieldLabel>
              <Input id="rule-to" type="date" {...register('valid_to')} />
            </Field>
          </div>
        ) : (
          <Button type="button" variant="link" size="sm" className="self-start px-0" onClick={() => setShowValidity(true)}>
            Только часть семестра…
          </Button>
        )}
      </FieldGroup>

      <DialogFooter className="flex-row flex-wrap items-center gap-2">
        {rule && (
          <>
            <ConfirmButton title="Удалить пару из сетки?" onConfirm={() => deleteRule.mutate(rule.id, { onSuccess: onDone })}>
              <Button type="button" variant="ghost" size="icon" aria-label="Удалить пару" className="text-destructive">
                <Trash2Icon />
              </Button>
            </ConfirmButton>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <CopyIcon /> Копировать
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onSelect={copyToOtherParity}>
                  <SplitIcon />
                  {rule.parity === 'all' ? 'Разделить по чётности' : `На ${RULE_PARITY_LABEL[oppositeParity(rule.parity)].toLowerCase()}`}
                </DropdownMenuItem>
                <DropdownMenuLabel>На день</DropdownMenuLabel>
                {WEEKDAYS_SHORT.map((d, i) =>
                  i + 1 === rule.weekday ? null : (
                    <DropdownMenuItem key={d} onSelect={() => copyToDay(i + 1)}>
                      {WEEKDAYS_FULL[i]}
                    </DropdownMenuItem>
                  ),
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
        <Button type="submit" disabled={saving} className="ml-auto">
          {saving ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </DialogFooter>
    </form>
  )
}
