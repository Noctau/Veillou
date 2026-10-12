import { ChevronDownIcon, ChevronUpIcon, CopyIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { compactValues } from '@/features/areas/fields'
import { FieldValuesForm } from '@/features/areas/FieldValuesForm'
import { type Area, type FieldValues, selectableAreas, useAreas, useAreaTypes, useCreateArea } from '@/features/areas/useAreas'
import { EventRulesEditor } from '@/features/eventrules/EventRulesEditor'
import { PALETTE, paletteColor } from '@/lib/colors'
import { PATTERN_LABEL, SCHEDULE_UI as T } from '@/lib/terms'
import { WEEKDAYS_FULL, WEEKDAYS_SHORT } from '@/lib/time'
import { cn } from '@/lib/utils'

import { EventTypeDialog } from './EventTypesSection'
import { NO_PERIOD } from './useCurrentPeriod'
import {
  groupGrids,
  type Pattern,
  type Period,
  ruleToCreate,
  type ScheduleRule,
  type ScheduleRuleCreate,
  slotsFor,
  useCreateScheduleRule,
  useDeleteScheduleRule,
  useEventTypes,
  usePeriods,
  useSlotGrids,
  useUpdateScheduleRule,
} from './useSchedule'

const NONE = 'none'
const NEW_AREA = '__new__'
type Kind = Pattern['kind']
type TimeMode = 'time' | 'slots'

/** Что подставить в новое правило (клетка сетки, клик в календаре). */
export type RuleDraft = {
  weekday?: number
  slot?: number
  cycleWeek?: number
  start?: string
  end?: string
  date?: string
  eventTypeId?: string
  areaId?: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Период новых правил (null — без периода). */
  periodId: string | null
  rule?: ScheduleRule
  draft?: RuleDraft
  /** Неделя цикла, показанная в сетке (для «разделить по неделям»). */
  viewCycleWeek?: number
  onEditRule?: (rule: ScheduleRule) => void
}

export function ScheduleRuleDialog(props: Props) {
  const { open, onOpenChange, rule } = props
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{rule ? T.editRule : T.newRule}</DialogTitle>
        </DialogHeader>
        {open && <RuleForm key={rule?.id ?? 'new'} {...props} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function plusHour(t: string): string {
  const [h, m] = t.split(':').map(Number)
  return `${String((h + 1) % 24).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function RuleForm({ periodId, rule, draft, viewCycleWeek, onEditRule, onDone }: Props & { onDone: () => void }) {
  const create = useCreateScheduleRule()
  const update = useUpdateScheduleRule()
  const remove = useDeleteScheduleRule()
  const createArea = useCreateArea()
  const { data: types = [] } = useEventTypes()
  const { data: periods = [] } = usePeriods()
  const { data: gridRows = [] } = useSlotGrids()
  const { data: allAreas } = useAreas()
  const { data: areaTypes = [] } = useAreaTypes()
  const [typeDialog, setTypeDialog] = useState(false)

  const p = rule?.pattern
  const [eventTypeId, setEventTypeId] = useState(rule?.event_type_id ?? draft?.eventTypeId ?? types[0]?.id ?? '')
  const [areaId, setAreaId] = useState<string>(rule?.area_id ?? draft?.areaId ?? NONE)
  const [newArea, setNewArea] = useState('')
  const [period, setPeriod] = useState<string>(rule ? (rule.period_id ?? NO_PERIOD) : (periodId ?? NO_PERIOD))
  const [kind, setKind] = useState<Kind>(p?.kind ?? (draft?.date ? 'once' : 'weekly'))
  const [weekdays, setWeekdays] = useState<number[]>(
    p?.kind === 'weekly' ? p.weekdays : draft?.weekday ? [draft.weekday] : [],
  )
  const [cycleWeeks, setCycleWeeks] = useState<number[]>(
    p?.kind === 'weekly' ? (p.cycle_weeks ?? []) : draft?.cycleWeek ? [draft.cycleWeek] : [],
  )
  const [on, setOn] = useState(p?.kind === 'day_cycle' ? p.on : 2)
  const [off, setOff] = useState(p?.kind === 'day_cycle' ? p.off : 2)
  const [anchor, setAnchor] = useState(p?.kind === 'day_cycle' ? p.anchor : (draft?.date ?? ''))
  const [onceDate, setOnceDate] = useState(p?.kind === 'once' ? p.date : (draft?.date ?? ''))
  const [rrule, setRrule] = useState(p?.kind === 'rrule' ? p.rrule : '')
  const [mode, setMode] = useState<TimeMode>(
    rule ? (rule.start_time ? 'time' : 'slots') : draft?.slot ? 'slots' : 'time',
  )
  const [start, setStart] = useState(rule?.start_time ?? draft?.start ?? '09:00')
  const [end, setEnd] = useState(rule?.end_time ?? draft?.end ?? plusHour(draft?.start ?? '09:00'))
  const [gridId, setGridId] = useState<string>(rule?.slot_grid_id ?? '')
  const [slotFrom, setSlotFrom] = useState<number | null>(rule?.slot_from ?? draft?.slot ?? null)
  const [slotTo, setSlotTo] = useState<number | null>(rule?.slot_to ?? null)
  const [location, setLocation] = useState(rule?.location ?? '')
  const [title, setTitle] = useState(rule?.title ?? '')
  const [note, setNote] = useState(rule?.note ?? '')
  const [validFrom, setValidFrom] = useState(rule?.valid_from ?? '')
  const [validTo, setValidTo] = useState(rule?.valid_to ?? '')
  const [fields, setFields] = useState<FieldValues>(rule?.fields ?? {})
  const [more, setMore] = useState(!!(rule?.title || rule?.note || rule?.valid_from || rule?.valid_to))
  const [error, setError] = useState<string | null>(null)

  const eventType = types.find((t) => t.id === eventTypeId)
  const selectedPeriod: Period | undefined = periods.find((x) => x.id === period)
  const cycle = selectedPeriod?.cycle_weeks ?? 1
  // Сетки этого периода и общие (без периода)
  const grids = groupGrids(gridRows).filter(
    (g) => g.period_id === (selectedPeriod?.id ?? null) || g.period_id === null,
  )
  const grid = grids.find((g) => g.id === gridId) ?? grids[0]
  const slots = slotsFor(grid, weekdays[0] ?? 1)
  const areas = selectableAreas(allAreas, areaId === NONE ? null : areaId)
  // Новая сфера — типа по умолчанию у типа занятости, иначе первого
  const newAreaType = areaTypes.find((t) => t.id === eventType?.default_area_type_id) ?? areaTypes[0]
  const saving = create.isPending || update.isPending || createArea.isPending

  const pattern = (): Pattern | string => {
    switch (kind) {
      case 'weekly':
        if (!weekdays.length) return T.daysRequired
        return { kind, weekdays, cycle_weeks: cycle > 1 && cycleWeeks.length ? cycleWeeks : null }
      case 'day_cycle':
        if (!anchor) return T.required
        return { kind, on, off, anchor }
      case 'once':
        if (!onceDate) return T.required
        return { kind, date: onceDate }
      case 'rrule':
        if (!rrule.trim()) return T.required
        return { kind, rrule: rrule.trim() }
    }
  }

  const body = async (): Promise<ScheduleRuleCreate | string> => {
    if (!eventTypeId) return T.noTypes
    const pat = pattern()
    if (typeof pat === 'string') return pat
    if (mode === 'time' && start === end) return T.sameTime
    if (mode === 'slots' && (!grid || slotFrom === null)) return T.slotRequired
    let area: string | null = areaId === NONE ? null : areaId
    if (areaId === NEW_AREA) {
      if (!newArea.trim() || !newAreaType) return T.required
      const created = await createArea.mutateAsync({
        area_type_id: newAreaType.id,
        name: newArea.trim(),
        period_id: selectedPeriod?.id ?? null,
        color: PALETTE[(allAreas?.length ?? 0) % PALETTE.length].hex,
        notes: '',
      })
      area = created.id
    }
    return {
      event_type_id: eventTypeId,
      area_id: area,
      period_id: selectedPeriod?.id ?? null,
      pattern: pat,
      start_time: mode === 'time' ? start : null,
      end_time: mode === 'time' ? end : null,
      slot_grid_id: mode === 'slots' ? (grid?.id ?? null) : null,
      slot_from: mode === 'slots' ? slotFrom : null,
      slot_to: mode === 'slots' && slotTo !== null && slotFrom !== null && slotTo > slotFrom ? slotTo : null,
      valid_from: validFrom || null,
      valid_to: validTo || null,
      title: title.trim() || null,
      location: location.trim() || null,
      fields: compactValues(fields),
      note,
    }
  }

  const submit = async () => {
    setError(null)
    try {
      const data = await body()
      if (typeof data === 'string') {
        setError(data)
        return
      }
      if (rule) await update.mutateAsync({ id: rule.id, body: data })
      else await create.mutateAsync(data)
      onDone()
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  }

  const copy = async (change: Partial<ScheduleRuleCreate>, split?: Partial<ScheduleRuleCreate>) => {
    if (!rule) return
    try {
      const created = await create.mutateAsync({ ...ruleToCreate(rule), ...change })
      if (split) await update.mutateAsync({ id: rule.id, body: split })
      toast.success(T.copied)
      onEditRule?.(created)
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  }

  if (!types.length) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">{T.noTypes}</p>
        <Button variant="outline" onClick={() => setTypeDialog(true)}>
          <PlusIcon /> {T.eventType}
        </Button>
        <EventTypeDialog open={typeDialog} onOpenChange={setTypeDialog} onCreated={(t) => setEventTypeId(t.id)} />
      </div>
    )
  }

  const weekly = rule?.pattern.kind === 'weekly' ? rule.pattern : null

  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <FieldGroup>
        <div className="grid grid-cols-2 gap-4">
          <Field>
            <FieldLabel htmlFor="rule-type">{T.eventType}</FieldLabel>
            <Select value={eventTypeId} onValueChange={setEventTypeId}>
              <SelectTrigger id="rule-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {types.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    <span className={cn('size-2.5 rounded-full', paletteColor(t.color).bg)} />
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="rule-area">{newAreaType?.name ?? T.area}</FieldLabel>
            <Select value={areaId} onValueChange={setAreaId}>
              <SelectTrigger id="rule-area" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{T.noArea}</SelectItem>
                {areas.map((a: Area) => (
                  <SelectItem key={a.id} value={a.id}>
                    <span className={cn('size-2.5 rounded-full', paletteColor(a.color).bg)} />
                    {a.name}
                  </SelectItem>
                ))}
                {newAreaType && <SelectItem value={NEW_AREA}>{T.newArea(newAreaType.name)}</SelectItem>}
              </SelectContent>
            </Select>
          </Field>
        </div>
        {areaId === NEW_AREA && (
          <Input autoFocus placeholder={T.name} aria-label={T.name} value={newArea} onChange={(e) => setNewArea(e.target.value)} />
        )}

        <Field>
          <FieldLabel>{T.pattern}</FieldLabel>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            className="flex-wrap justify-start"
            value={kind}
            onValueChange={(v) => v && setKind(v as Kind)}
          >
            {(Object.keys(PATTERN_LABEL) as Kind[]).map((k) => (
              <ToggleGroupItem key={k} value={k} className="px-3">
                {PATTERN_LABEL[k]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        {kind === 'weekly' && (
          <>
            <ToggleGroup
              type="multiple"
              variant="outline"
              size="sm"
              className="w-full"
              aria-label={T.weekdays}
              value={weekdays.map(String)}
              onValueChange={(v) => setWeekdays(v.map(Number).sort((a, b) => a - b))}
            >
              {WEEKDAYS_SHORT.map((d, i) => (
                <ToggleGroupItem key={d} value={String(i + 1)} className="flex-1">
                  {d}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {cycle > 1 && (
              <Field>
                <FieldLabel>{T.weeks}</FieldLabel>
                <ToggleGroup
                  type="multiple"
                  variant="outline"
                  size="sm"
                  className="flex-wrap justify-start"
                  value={cycleWeeks.map(String)}
                  onValueChange={(v) => setCycleWeeks(v.map(Number).sort((a, b) => a - b))}
                >
                  {Array.from({ length: cycle }, (_, i) => (
                    <ToggleGroupItem key={i} value={String(i + 1)} className="px-3">
                      {T.cycleWeek(i + 1)}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
                <FieldDescription>{cycleWeeks.length ? null : T.everyWeek}</FieldDescription>
              </Field>
            )}
          </>
        )}
        {kind === 'day_cycle' && (
          <div className="grid grid-cols-3 gap-2">
            <Field>
              <FieldLabel htmlFor="rule-on">{T.on}</FieldLabel>
              <Input id="rule-on" type="number" min={1} max={365} value={on} onChange={(e) => setOn(Math.max(1, Number(e.target.value) || 1))} />
            </Field>
            <Field>
              <FieldLabel htmlFor="rule-off">{T.off}</FieldLabel>
              <Input id="rule-off" type="number" min={0} max={365} value={off} onChange={(e) => setOff(Math.max(0, Number(e.target.value) || 0))} />
            </Field>
            <Field>
              <FieldLabel htmlFor="rule-anchor">{T.anchor}</FieldLabel>
              <Input id="rule-anchor" type="date" value={anchor} onChange={(e) => setAnchor(e.target.value)} />
            </Field>
          </div>
        )}
        {kind === 'once' && (
          <Field>
            <FieldLabel htmlFor="rule-date">{T.date}</FieldLabel>
            <Input id="rule-date" type="date" value={onceDate} onChange={(e) => setOnceDate(e.target.value)} />
          </Field>
        )}
        {kind === 'rrule' && (
          <Field>
            <FieldLabel htmlFor="rule-rrule">{T.rrule}</FieldLabel>
            <Input id="rule-rrule" placeholder="FREQ=MONTHLY;BYDAY=2TU" value={rrule} onChange={(e) => setRrule(e.target.value)} />
            <FieldDescription>{T.rruleHint}</FieldDescription>
          </Field>
        )}

        <Field>
          <FieldLabel>{T.time}</FieldLabel>
          {grids.length > 0 && (
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              className="justify-start"
              value={mode}
              onValueChange={(v) => v && setMode(v as TimeMode)}
            >
              <ToggleGroupItem value="time" className="px-3">
                {T.byTime}
              </ToggleGroupItem>
              <ToggleGroupItem value="slots" className="px-3">
                {T.bySlots}
              </ToggleGroupItem>
            </ToggleGroup>
          )}
          {mode === 'time' ? (
            <>
              <div className="flex items-center gap-2">
                <Input type="time" step={300} aria-label={T.start} value={start} onChange={(e) => setStart(e.target.value)} />
                <span className="text-muted-foreground">—</span>
                <Input type="time" step={300} aria-label={T.end} value={end} onChange={(e) => setEnd(e.target.value)} />
              </div>
              {end < start && <FieldDescription>{T.overnightHint}</FieldDescription>}
            </>
          ) : (
            <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2">
              {grids.length > 1 ? (
                <Select value={grid?.id ?? ''} onValueChange={setGridId}>
                  <SelectTrigger aria-label={T.grid} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {grids.map((g) => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <span className="text-sm text-muted-foreground">{grid?.name}</span>
              )}
              {[
                { label: T.slotFrom, value: slotFrom, set: setSlotFrom },
                { label: T.slotTo, value: slotTo, set: setSlotTo },
              ].map((s) => (
                <Select
                  key={s.label}
                  value={s.value === null ? '' : String(s.value)}
                  onValueChange={(v) => s.set(Number(v))}
                >
                  <SelectTrigger aria-label={s.label} className="w-auto">
                    <SelectValue placeholder={s.label} />
                  </SelectTrigger>
                  <SelectContent>
                    {slots.map((slot) => (
                      <SelectItem key={slot.number} value={String(slot.number)}>
                        {slot.number} · {slot.start}–{slot.end}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ))}
            </div>
          )}
        </Field>

        <Field>
          <FieldLabel htmlFor="rule-location">{T.location}</FieldLabel>
          <Input id="rule-location" maxLength={200} value={location} onChange={(e) => setLocation(e.target.value)} />
        </Field>
        {eventType && eventType.fields.length > 0 && (
          <FieldValuesForm defs={eventType.fields} value={fields} onChange={setFields} areas={allAreas} idPrefix="rule-field" />
        )}
        {rule && (
          <EventRulesEditor
            owner={{ schedule_rule_id: rule.id }}
            fieldLabels={eventType?.fields.map((f) => f.label) ?? []}
          />
        )}

        <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setMore(!more)}>
          {more ? <ChevronUpIcon /> : <ChevronDownIcon />} {T.validity}
        </Button>
        {more && (
          <>
            <Field>
              <FieldLabel htmlFor="rule-period">{T.period}</FieldLabel>
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger id="rule-period" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_PERIOD}>{T.noPeriod}</SelectItem>
                  {periods.map((x) => (
                    <SelectItem key={x.id} value={x.id}>
                      {x.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field>
                <FieldLabel htmlFor="rule-from">{T.validFrom}</FieldLabel>
                <Input id="rule-from" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="rule-to">{T.validTo}</FieldLabel>
                <Input id="rule-to" type="date" min={validFrom} value={validTo} onChange={(e) => setValidTo(e.target.value)} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="rule-title">{T.ruleTitle}</FieldLabel>
              <Input id="rule-title" maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} />
              <FieldDescription>{T.titleHint}</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="rule-note">{T.note}</FieldLabel>
              <Textarea id="rule-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
          </>
        )}
        {error && <FieldError>{error}</FieldError>}
      </FieldGroup>

      <DialogFooter className="flex-row flex-wrap items-center gap-2">
        {rule && (
          <>
            <ConfirmButton
              title={T.deleteTitle}
              description={T.deleteDescription}
              onConfirm={() => remove.mutate(rule.id, { onSuccess: onDone })}
            >
              <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
                <Trash2Icon />
              </Button>
            </ConfirmButton>
            {weekly && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button type="button" variant="outline" size="sm">
                    <CopyIcon /> {T.copy}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {cycle > 1 && (
                    <>
                      <DropdownMenuLabel>{T.copyToWeek}</DropdownMenuLabel>
                      {Array.from({ length: cycle }, (_, i) => i + 1)
                        .filter((w) => !weekly.cycle_weeks?.includes(w))
                        .map((w) => (
                          <DropdownMenuItem
                            key={w}
                            onSelect={() => {
                              // «Каждую неделю» → своя неделя остаётся, копия — на выбранную
                              const mine = viewCycleWeek && viewCycleWeek !== w ? viewCycleWeek : null
                              const split = !weekly.cycle_weeks?.length && mine
                              void copy(
                                { pattern: { ...weekly, cycle_weeks: [w] } },
                                split ? { pattern: { ...weekly, cycle_weeks: [mine] } } : undefined,
                              )
                            }}
                          >
                            {T.cycleWeek(w)}
                          </DropdownMenuItem>
                        ))}
                    </>
                  )}
                  <DropdownMenuLabel>{T.copyToDay}</DropdownMenuLabel>
                  {WEEKDAYS_FULL.map((d, i) =>
                    weekly.weekdays.includes(i + 1) ? null : (
                      <DropdownMenuItem key={d} onSelect={() => void copy({ pattern: { ...weekly, weekdays: [i + 1] } })}>
                        {d}
                      </DropdownMenuItem>
                    ),
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </>
        )}
        <Button type="submit" disabled={saving} className="ml-auto">
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
