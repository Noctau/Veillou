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
import { type Area, useAreaTypes, useCreateArea } from '@/features/areas/useAreas'
import { PALETTE, paletteColor } from '@/lib/colors'
import { AREAS_UI, CLASS_TYPE_LABEL, RULE_PARITY_LABEL } from '@/lib/terms'
import { cn } from '@/lib/utils'
import { WEEKDAYS_FULL, WEEKDAYS_SHORT } from '@/lib/time'

import { oppositeParity } from './parity'
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

const NEW_AREA = '__new__'
const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'ЧЧ:ММ')

const schema = z
  .object({
    area_id: z.string().min(1, 'Выберите сферу'),
    new_area: z.string().trim(),
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
  .refine((v) => v.area_id !== NEW_AREA || v.new_area.length > 0, {
    message: 'Название сферы',
    path: ['new_area'],
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
  areas: Area[]
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

function toForm(rule: ClassRule | undefined, draft: RuleDraft | undefined, areas: Area[]): FormValues {
  return {
    area_id: rule?.area_id ?? (areas.length ? '' : NEW_AREA),
    new_area: '',
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
  areas,
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
  const createArea = useCreateArea()
  const { data: areaTypes } = useAreaTypes()
  // Новая сфера — того же типа, что и сферы в сетке (или первого)
  const newAreaType = areaTypes?.find((t) => areas.some((a) => a.area_type_id === t.id)) ?? areaTypes?.[0]
  const [showValidity, setShowValidity] = useState(!!(rule?.valid_from || rule?.valid_to))

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: toForm(rule, draft, areas),
  })
  const { register, control, formState } = form
  const { errors } = formState
  const weekday = useWatch({ control, name: 'weekday' })
  const customTime = useWatch({ control, name: 'custom_time' })
  const areaId = useWatch({ control, name: 'area_id' })
  const slots = bellsFor(weekday)
  const saving = createRule.isPending || updateRule.isPending || createArea.isPending

  const body = (v: FormValues, area_id: string): ClassRuleCreate => ({
    semester_id: semesterId,
    area_id,
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
    let area_id = v.area_id
    try {
      if (area_id === NEW_AREA) {
        if (!newAreaType) {
          toast.error(AREAS_UI.noTypes)
          return
        }
        const created = await createArea.mutateAsync({
          area_type_id: newAreaType.id,
          name: v.new_area,
          period_id: semesterId,
          color: PALETTE[areas.length % PALETTE.length].hex,
          notes: '',
        })
        area_id = created.id
      }
      const data = body(v, area_id)
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
    try {
      await createRule.mutateAsync({ ...rest, weekday: target })
      toast.success(`Скопировано на ${WEEKDAYS_FULL[target - 1].toLowerCase()}`)
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  }

  /** «Другая чётность»: копия с противоположной чётностью (у «каждой недели» — разделить). */
  const copyToOtherParity = async () => {
    if (!rule) return
    const { id: _, ...rest } = rule
    const mine: Parity = rule.parity === 'all' ? viewParity : rule.parity
    try {
      // Сначала копия: если она не создастся, исходная пара останется «каждую неделю»
      const copy = await createRule.mutateAsync({ ...rest, parity: oppositeParity(mine) })
      if (rule.parity === 'all') await updateRule.mutateAsync({ id: rule.id, body: { parity: mine } })
      toast.success('Копия создана — поправьте её')
      onEditRule(copy)
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <FieldGroup>
        <Field data-invalid={!!errors.area_id}>
          <FieldLabel htmlFor="rule-area">{newAreaType?.name ?? 'Сфера'}</FieldLabel>
          <Controller
            control={control}
            name="area_id"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="rule-area" className="w-full">
                  <SelectValue placeholder="Выберите сферу" />
                </SelectTrigger>
                <SelectContent
                  onCloseAutoFocus={(e) => {
                    // «Новая сфера» -> сразу в поле названия, а не обратно на селект
                    if (form.getValues('area_id') === NEW_AREA) {
                      e.preventDefault()
                      form.setFocus('new_area')
                    }
                  }}
                >
                  {areas.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      <span className={cn('size-2.5 rounded-full', paletteColor(s.color).bg)} />
                      {s.name}
                    </SelectItem>
                  ))}
                  {newAreaType && <SelectItem value={NEW_AREA}>＋ {newAreaType.name}</SelectItem>}
                </SelectContent>
              </Select>
            )}
          />
          {errors.area_id && <FieldError>{errors.area_id.message}</FieldError>}
        </Field>
        {areaId === NEW_AREA && (
          <Field data-invalid={!!errors.new_area}>
            <Input
              placeholder="Название"
              aria-label="Название новой сферы"
              {...register('new_area')}
            />
            {errors.new_area && <FieldError>{errors.new_area.message}</FieldError>}
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
