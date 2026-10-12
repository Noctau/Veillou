import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useRef, useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldContent, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { TaskTypeSelect } from '@/features/catalog/CatalogSelect'
import { EVENT_RULES_UI as T } from '@/lib/terms'

import {
  type EventRule,
  type EventRuleCreate,
  type Owner,
  useCreateEventRule,
  useDeleteEventRule,
  useEventRules,
  useUpdateEventRule,
} from './useEventRules'

type When = 'before' | 'after'
type Unit = 'min' | 'h' | 'd'
const UNIT_MIN: Record<Unit, number> = { min: 1, h: 60, d: 1440 }

function splitOffset(minutes: number): [number, Unit] {
  if (minutes && minutes % 1440 === 0) return [minutes / 1440, 'd']
  if (minutes && minutes % 60 === 0) return [minutes / 60, 'h']
  return [minutes, 'min']
}

function offsetText(minutes: number): string {
  const [n, unit] = splitOffset(minutes)
  return n ? `${n} ${T.units[unit]}` : ''
}

function summary(rule: EventRule): string {
  if (rule.when === 'before') return T.summaryBefore(offsetText(rule.offset_min))
  return T.summaryAfter(
    [rule.within_days !== null ? T.withinChip(rule.within_days) : '', rule.until_next ? T.untilNextChip : ''].filter(
      Boolean,
    ),
  )
}

function RuleForm({
  owner,
  rule,
  fieldLabels,
  onDone,
}: {
  owner: Owner
  rule?: EventRule
  fieldLabels: string[]
  onDone: () => void
}) {
  const create = useCreateEventRule()
  const update = useUpdateEventRule()
  const remove = useDeleteEventRule()
  const input = useRef<HTMLInputElement>(null)
  const [when, setWhen] = useState<When>(rule?.when ?? 'before')
  const [template, setTemplate] = useState(rule?.title_template ?? '')
  const [estimate, setEstimate] = useState(rule?.estimate_min ?? 30)
  const [initialN, initialUnit] = splitOffset(rule?.offset_min ?? 30)
  const [offsetN, setOffsetN] = useState(initialN)
  const [unit, setUnit] = useState<Unit>(initialUnit)
  const [within, setWithin] = useState<number | null>(rule ? rule.within_days : 2)
  const [untilNext, setUntilNext] = useState(rule?.until_next ?? false)
  const [confirm, setConfirm] = useState(rule?.confirm ?? false)
  const [taskTypeId, setTaskTypeId] = useState<string | null>(rule?.task_type_id ?? null)
  const saving = create.isPending || update.isPending
  const valid = template.trim() !== '' && estimate >= 5 && offsetN >= 0

  const insert = (token: string) => {
    const el = input.current
    const at = el?.selectionStart ?? template.length
    const next = template.slice(0, at) + token + template.slice(el?.selectionEnd ?? at)
    setTemplate(next)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(at + token.length, at + token.length)
    })
  }

  const save = () => {
    const body = {
      when,
      title_template: template.trim(),
      estimate_min: estimate,
      task_type_id: taskTypeId,
      offset_min: when === 'before' ? offsetN * UNIT_MIN[unit] : 0,
      within_days: when === 'after' ? within : null,
      until_next: when === 'after' && untilNext,
      confirm,
    }
    if (rule) update.mutate({ id: rule.id, body }, { onSuccess: onDone })
    else create.mutate({ ...owner, ...body } as EventRuleCreate, { onSuccess: onDone })
  }

  const tokens = [`{${T.tokenArea}}`, `{${T.tokenEvent}}`, ...fieldLabels.map((l) => `{поле:${l}}`)]

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        e.stopPropagation()
        if (valid) save()
      }}
    >
      <Field>
        <FieldLabel>{T.when}</FieldLabel>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="justify-start"
          value={when}
          onValueChange={(v) => v && setWhen(v as When)}
        >
          {(['before', 'after'] as const).map((w) => (
            <ToggleGroupItem key={w} value={w} className="px-3">
              {T.whenOptions[w]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <Field>
        <FieldLabel htmlFor="er-template">{T.template}</FieldLabel>
        <Input
          id="er-template"
          ref={input}
          autoFocus={!rule}
          maxLength={300}
          placeholder={T.templatePlaceholder}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">{T.insert}</span>
          {tokens.map((token) => (
            <Button
              key={token}
              type="button"
              variant="secondary"
              size="sm"
              className="h-6 rounded-full px-2 text-xs"
              onClick={() => insert(token)}
            >
              {token.slice(1, -1)}
            </Button>
          ))}
        </div>
      </Field>
      {when === 'before' ? (
        <Field>
          <FieldLabel htmlFor="er-offset">{T.finishBefore}</FieldLabel>
          <div className="flex items-center gap-2">
            <Input
              id="er-offset"
              type="number"
              inputMode="numeric"
              min={0}
              className="w-20"
              value={offsetN}
              onChange={(e) => setOffsetN(Math.max(0, Math.round(Number(e.target.value) || 0)))}
            />
            <Select value={unit} onValueChange={(v) => setUnit(v as Unit)}>
              <SelectTrigger className="w-24" aria-label={T.finishBefore}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(['min', 'h', 'd'] as const).map((u) => (
                  <SelectItem key={u} value={u}>
                    {T.units[u]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </Field>
      ) : (
        <>
          <Field>
            <FieldLabel htmlFor="er-within">{T.withinDays}</FieldLabel>
            <div className="flex items-center gap-2">
              <Input
                id="er-within"
                type="number"
                inputMode="numeric"
                min={0}
                max={60}
                className="w-20"
                value={within ?? ''}
                onChange={(e) =>
                  setWithin(e.target.value === '' ? null : Math.max(0, Math.min(60, Math.round(Number(e.target.value)))))
                }
              />
              <span className="text-sm text-muted-foreground">{T.days}</span>
            </div>
          </Field>
          <Field orientation="horizontal">
            <FieldContent>
              <FieldLabel htmlFor="er-next">{T.untilNext}</FieldLabel>
            </FieldContent>
            <Switch id="er-next" checked={untilNext} onCheckedChange={setUntilNext} />
          </Field>
        </>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="er-estimate">{T.estimate}</FieldLabel>
          <div className="flex items-center gap-2">
            <Input
              id="er-estimate"
              type="number"
              inputMode="numeric"
              min={5}
              step={5}
              className="w-20"
              value={estimate}
              onChange={(e) => setEstimate(Math.round(Number(e.target.value) || 0))}
            />
            <span className="text-sm text-muted-foreground">{T.minutes}</span>
          </div>
        </Field>
        <Field>
          <FieldLabel htmlFor="er-type">{T.taskType}</FieldLabel>
          <TaskTypeSelect id="er-type" value={taskTypeId} onChange={setTaskTypeId} emptyLabel={T.noTaskType} />
        </Field>
      </div>
      <Field orientation="horizontal">
        <FieldContent>
          <FieldLabel htmlFor="er-confirm">{T.confirm}</FieldLabel>
          <FieldDescription>{T.confirmHint}</FieldDescription>
        </FieldContent>
        <Switch id="er-confirm" checked={confirm} onCheckedChange={setConfirm} />
      </Field>
      <DialogFooter className="flex-row items-center">
        {rule && (
          <ConfirmButton
            title={T.deleteTitle}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(rule.id, { onSuccess: onDone })}
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

/** «Автозадачи» в редакторе типа занятости и правила расписания (M19.2). */
export function EventRulesEditor({ owner, fieldLabels = [] }: { owner: Owner; fieldLabels?: string[] }) {
  const { data: rules = [] } = useEventRules(owner)
  const [editing, setEditing] = useState<{ rule?: EventRule } | null>(null)

  return (
    <Field>
      <div className="flex items-center justify-between">
        <FieldLabel>{T.title}</FieldLabel>
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing({})}>
          <PlusIcon /> {T.add}
        </Button>
      </div>
      <FieldDescription>{T.hint}</FieldDescription>
      {rules.length > 0 && (
        <ul className="flex flex-col">
          {rules.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => setEditing({ rule: r })}
                className="flex w-full flex-col items-start rounded-lg px-2 py-1.5 text-left hover:bg-muted"
              >
                <span className="text-sm">{r.title_template}</span>
                <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  {summary(r)} · {r.estimate_min} {T.minutes}
                  {r.confirm && <Badge variant="secondary">{T.confirmChip}</Badge>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing?.rule ? T.editTitle : T.newTitle}</DialogTitle>
          </DialogHeader>
          {editing && (
            <RuleForm
              key={editing.rule?.id ?? 'new'}
              owner={owner}
              rule={editing.rule}
              fieldLabels={fieldLabels}
              onDone={() => setEditing(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </Field>
  )
}
