import { ChevronDownIcon, ChevronUpIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldContent, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { CHOICE_TYPES, type FieldDraft, fromDraft, toDraft } from '@/features/areas/fields'
import { FieldDefsEditor } from '@/features/areas/FieldDefsEditor'
import { CategoryIcon } from '@/features/catalog/CategoryIcon'
import { IconPicker } from '@/features/catalog/IconPicker'
import { type CategoryIconName, useBudgets, useUpdateBudget } from '@/features/catalog/useCatalog'
import { EventRulesEditor } from '@/features/eventrules/EventRulesEditor'
import { paletteColor } from '@/lib/colors'
import { CHANNEL_LABEL, EVENT_RULES_UI, EVENT_TYPES_UI as T } from '@/lib/terms'
import { cn } from '@/lib/utils'

import {
  type Channel,
  type EventType,
  type EventTypeCreate,
  useCreateEventType,
  useDeleteEventType,
  useEventTypes,
  useUpdateEventType,
} from './useSchedule'

const CHANNELS = Object.keys(CHANNEL_LABEL) as Channel[]

function Flag({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <Field orientation="horizontal">
      <FieldContent>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <FieldDescription>{hint}</FieldDescription>
      </FieldContent>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </Field>
  )
}

function MinutesInput({ id, value, onChange, label }: { id: string; value: number; onChange: (v: number) => void; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <Input
        id={id}
        aria-label={label}
        type="number"
        inputMode="numeric"
        min={0}
        max={240}
        step={5}
        value={value}
        onChange={(e) => onChange(Math.max(0, Math.min(240, Math.round(Number(e.target.value) || 0))))}
        className="w-20"
      />
      <span className="text-sm text-muted-foreground">{T.minutes}</span>
    </div>
  )
}

/** Редактор типа занятости: базовое сразу, остальное под «Подробнее». */
function EventTypeForm({ eventType, onDone }: { eventType?: EventType; onDone: (created?: EventType) => void }) {
  const create = useCreateEventType()
  const update = useUpdateEventType()
  const remove = useDeleteEventType()
  const updateBudget = useUpdateBudget()
  const { data: budgets = [] } = useBudgets()
  const [name, setName] = useState(eventType?.name ?? '')
  const [plural, setPlural] = useState(eventType?.name_plural ?? '')
  const [icon, setIcon] = useState<CategoryIconName>(eventType?.icon ?? 'calendar')
  const [color, setColor] = useState(eventType?.color ?? '#64748b')
  const [remind, setRemind] = useState<number | null>(eventType ? eventType.remind_before_min : 15)
  const [channels, setChannels] = useState<Channel[]>(eventType?.remind_channels ?? ['push', 'telegram'])
  const [before, setBefore] = useState(eventType?.buffer_before_min ?? 0)
  const [after, setAfter] = useState(eventType?.buffer_after_min ?? 0)
  const [merge, setMerge] = useState(eventType?.merge_buffers ?? false)
  const [nowNext, setNowNext] = useState(eventType?.show_now_next ?? false)
  const [rest, setRest] = useState(eventType?.is_rest ?? false)
  const [prep, setPrep] = useState(eventType?.supports_prep ?? false)
  const [label, setLabel] = useState(eventType?.location_label ?? '')
  const [fields, setFields] = useState<FieldDraft[]>(() => eventType?.fields.map(toDraft) ?? [])
  const initialBudgets = budgets.filter((b) => eventType && b.event_type_ids.includes(eventType.id)).map((b) => b.id)
  const [budgetIds, setBudgetIds] = useState<string[]>(initialBudgets)
  const [more, setMore] = useState(false)
  const saving = create.isPending || update.isPending || updateBudget.isPending
  const valid =
    name.trim() !== '' &&
    (remind === null || channels.length > 0) &&
    fields.every((f) => f.label.trim() !== '' && (!CHOICE_TYPES.has(f.type) || (fromDraft(f).options ?? []).length > 0))

  const syncBudgets = async (typeId: string) => {
    for (const b of budgets) {
      const has = b.event_type_ids.includes(typeId)
      const want = budgetIds.includes(b.id)
      if (has === want) continue
      const ids = want ? [...b.event_type_ids, typeId] : b.event_type_ids.filter((id) => id !== typeId)
      await updateBudget.mutateAsync({ id: b.id, body: { event_type_ids: ids } })
    }
  }

  const save = async () => {
    const body: EventTypeCreate = {
      name: name.trim(),
      name_plural: plural.trim() || null,
      icon,
      color,
      remind_before_min: remind,
      remind_channels: channels,
      buffer_before_min: before,
      buffer_after_min: after,
      merge_buffers: merge,
      show_now_next: nowNext,
      is_rest: rest,
      supports_prep: prep,
      location_label: label.trim(),
      fields: fields.map(fromDraft),
    }
    try {
      const saved = eventType
        ? await update.mutateAsync({ id: eventType.id, body: { ...body, name_plural: plural.trim() || name.trim() } })
        : await create.mutateAsync(body)
      await syncBudgets(saved.id)
      onDone(eventType ? undefined : saved)
    } catch {
      // ошибка уже показана тостом в onError мутации
    }
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) void save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="et-name">{T.name}</FieldLabel>
        <Input
          id="et-name"
          autoFocus={!eventType}
          placeholder={T.namePlaceholder}
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel>{T.color}</FieldLabel>
        <ColorPicker value={color} onChange={(c) => c && setColor(c)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="et-remind">{T.remind}</FieldLabel>
        <div className="flex flex-wrap items-center gap-3">
          {remind !== null && <MinutesInput id="et-remind" label={T.remind} value={remind} onChange={setRemind} />}
          <div className="flex items-center gap-2">
            <Checkbox id="et-remind-off" checked={remind === null} onCheckedChange={(v) => setRemind(v === true ? null : 15)} />
            <FieldLabel htmlFor="et-remind-off" className="font-normal">
              {T.remindOff}
            </FieldLabel>
          </div>
        </div>
      </Field>
      <Field>
        <FieldLabel htmlFor="et-before">{T.buffer}</FieldLabel>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">{T.bufferBefore}</span>
          <MinutesInput id="et-before" label={`${T.buffer} ${T.bufferBefore}`} value={before} onChange={setBefore} />
          <span className="text-sm text-muted-foreground">{T.bufferAfter}</span>
          <MinutesInput id="et-after" label={`${T.buffer} ${T.bufferAfter}`} value={after} onChange={setAfter} />
        </div>
      </Field>

      <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setMore(!more)}>
        {more ? <ChevronUpIcon /> : <ChevronDownIcon />} {more ? T.less : T.more}
      </Button>
      {more && (
        <div className="flex flex-col gap-5">
          <Field>
            <FieldLabel htmlFor="et-plural">{T.plural}</FieldLabel>
            <Input id="et-plural" placeholder={name} maxLength={100} value={plural} onChange={(e) => setPlural(e.target.value)} />
            <FieldDescription>{T.pluralHint}</FieldDescription>
          </Field>
          <Field>
            <FieldLabel>{T.icon}</FieldLabel>
            <IconPicker value={icon} onChange={setIcon} />
          </Field>
          {remind !== null && (
            <Field>
              <FieldLabel>{T.channels}</FieldLabel>
              <ToggleGroup
                type="multiple"
                variant="outline"
                size="sm"
                className="justify-start"
                value={channels}
                onValueChange={(v) => setChannels(v as Channel[])}
              >
                {CHANNELS.map((c) => (
                  <ToggleGroupItem key={c} value={c} className="px-3">
                    {CHANNEL_LABEL[c]}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Field>
          )}
          <Flag id="et-merge" label={T.merge} hint={T.mergeHint} checked={merge} onChange={setMerge} />
          <Flag id="et-now" label={T.nowNext} hint={T.nowNextHint} checked={nowNext} onChange={setNowNext} />
          <Flag id="et-rest" label={T.rest} hint={T.restHint} checked={rest} onChange={setRest} />
          <Flag id="et-prep" label={T.prep} hint={T.prepHint} checked={prep} onChange={setPrep} />
          <Field>
            <FieldLabel>{T.budgets}</FieldLabel>
            {budgets.length ? (
              <ToggleGroup
                type="multiple"
                variant="outline"
                size="sm"
                className="flex-wrap justify-start"
                value={budgetIds}
                onValueChange={setBudgetIds}
              >
                {budgets.map((b) => (
                  <ToggleGroupItem key={b.id} value={b.id} className="rounded-full! border px-3">
                    {b.name}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            ) : null}
            <FieldDescription>{budgets.length ? T.budgetsHint : T.noBudgets}</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="et-label">{T.locationLabel}</FieldLabel>
            <Input id="et-label" maxLength={20} className="w-32" value={label} onChange={(e) => setLabel(e.target.value)} />
            <FieldDescription>{T.locationLabelHint}</FieldDescription>
          </Field>
          <FieldDefsEditor value={fields} onChange={setFields} legend={T.fields} hint={T.fieldsHint} />
          {eventType ? (
            <EventRulesEditor owner={{ event_type_id: eventType.id }} fieldLabels={eventType.fields.map((f) => f.label)} />
          ) : (
            <FieldDescription>{EVENT_RULES_UI.saveFirst}</FieldDescription>
          )}
        </div>
      )}

      <DialogFooter className="flex-row items-center">
        {eventType && (
          <ConfirmButton
            title={T.deleteTitle(eventType.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(eventType.id, { onSuccess: () => onDone() })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" className="ml-auto" disabled={!valid || saving}>
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function EventTypeDialog({
  open,
  onOpenChange,
  eventType,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  eventType?: EventType
  onCreated?: (t: EventType) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{eventType?.name ?? T.newTitle}</DialogTitle>
        </DialogHeader>
        {open && (
          <EventTypeForm
            key={eventType?.id ?? 'new'}
            eventType={eventType}
            onDone={(created) => {
              onOpenChange(false)
              if (created) onCreated?.(created)
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Настройки → «Типы занятости» (M17.6). */
export function EventTypesSection() {
  const { data: types, isPending } = useEventTypes()
  const [editing, setEditing] = useState<{ eventType?: EventType } | null>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{T.title}</CardTitle>
        <CardDescription>{T.description}</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={() => setEditing({})}>
            <PlusIcon /> {T.add}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-16" />}
        {types && types.length === 0 && <p className="text-sm text-muted-foreground">{T.empty}</p>}
        <ul className="flex flex-col">
          {types?.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => setEditing({ eventType: t })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
              >
                <span className={cn('flex size-7 shrink-0 items-center justify-center rounded-md', paletteColor(t.color).bg)}>
                  <CategoryIcon name={t.icon} className="size-4 text-white" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{t.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[
                      t.remind_before_min !== null && T.remindChip(t.remind_before_min),
                      (t.buffer_before_min || t.buffer_after_min) &&
                        T.bufferChip(Math.max(t.buffer_before_min, t.buffer_after_min)),
                      t.fields.map((f) => f.label).join(', '),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
      <EventTypeDialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)} eventType={editing?.eventType} />
    </Card>
  )
}
