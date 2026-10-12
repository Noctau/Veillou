import { ArrowDownIcon, ArrowUpIcon, PlusIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { FieldDescription, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AREA_TYPES_UI as T, FIELD_TYPE_LABEL } from '@/lib/terms'

import { CHOICE_TYPES, type FieldDraft, MULTIPLE_TYPES, toDraft } from './fields'
import type { FieldType } from './useAreas'

const FIELD_TYPES = Object.keys(FIELD_TYPE_LABEL) as FieldType[]

/** Редактор описаний полей (FieldDef) — у типов сфер и типов занятости. */
function FieldRow({
  draft,
  onChange,
  onRemove,
  onMove,
  first,
  last,
}: {
  draft: FieldDraft
  onChange: (d: FieldDraft) => void
  onRemove: () => void
  onMove: (delta: -1 | 1) => void
  first: boolean
  last: boolean
}) {
  const id = `ft-${draft.key}`
  const flag = (name: 'multiple' | 'required' | 'show_in_reminder', label: string) => (
    <div className="flex items-center gap-2">
      <Checkbox id={`${id}-${name}`} checked={draft[name]} onCheckedChange={(v) => onChange({ ...draft, [name]: v === true })} />
      <Label htmlFor={`${id}-${name}`} className="font-normal">
        {label}
      </Label>
    </div>
  )
  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-center gap-1">
        <Input
          id={id}
          placeholder={T.fieldLabel}
          aria-label={T.fieldLabel}
          value={draft.label}
          maxLength={60}
          onChange={(e) => onChange({ ...draft, label: e.target.value })}
        />
        <Button type="button" variant="ghost" size="icon" aria-label={T.moveUp} disabled={first} onClick={() => onMove(-1)}>
          <ArrowUpIcon />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={T.moveDown} disabled={last} onClick={() => onMove(1)}>
          <ArrowDownIcon />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={T.removeField} onClick={onRemove}>
          <XIcon />
        </Button>
      </div>
      {/* Тип у сохранённого поля не меняется: старые значения стали бы мусором */}
      <Select value={draft.type} onValueChange={(v) => onChange({ ...draft, type: v as FieldType })} disabled={!!draft.id}>
        <SelectTrigger className="w-full" aria-label={T.fieldType}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {FIELD_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {FIELD_TYPE_LABEL[t]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {CHOICE_TYPES.has(draft.type) && (
        <Input
          placeholder={`${T.options}: ${T.optionsHint.toLowerCase()}`}
          aria-label={T.options}
          value={draft.options}
          onChange={(e) => onChange({ ...draft, options: e.target.value })}
        />
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
        {MULTIPLE_TYPES.has(draft.type) && flag('multiple', T.multiple)}
        {flag('required', T.required)}
        {flag('show_in_reminder', T.inReminder)}
      </div>
    </li>
  )
}

export function FieldDefsEditor({
  value,
  onChange,
  hint = T.fieldsHint,
  legend = T.fields,
}: {
  value: FieldDraft[]
  onChange: (v: FieldDraft[]) => void
  hint?: string
  legend?: string
}) {
  const move = (i: number, delta: -1 | 1) => {
    const next = [...value]
    ;[next[i], next[i + delta]] = [next[i + delta], next[i]]
    onChange(next)
  }
  return (
    <FieldSet>
      <FieldLegend variant="label">{legend}</FieldLegend>
      <FieldDescription>{hint}</FieldDescription>
      <ul className="flex flex-col gap-2">
        {value.map((d, i) => (
          <FieldRow
            key={d.key}
            draft={d}
            first={i === 0}
            last={i === value.length - 1}
            onChange={(next) => onChange(value.map((x, j) => (j === i ? next : x)))}
            onRemove={() => onChange(value.filter((_, j) => j !== i))}
            onMove={(delta) => move(i, delta)}
          />
        ))}
      </ul>
      {value.some((d) => d.id) && <FieldDescription>{T.removeFieldHint}</FieldDescription>}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, toDraft()])}>
        <PlusIcon /> {T.addField}
      </Button>
    </FieldSet>
  )
}
