import { PlusIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Field, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { CONTACT_LABEL, FIELDS_UI } from '@/lib/terms'

import type { Contact, LinkValue } from './fields'
import type { Area, FieldDef, FieldValues } from './useAreas'

const NONE = 'none'
const CONTACT_KEYS = ['name', 'role', 'phone', 'email', 'link', 'note'] as const
const CONTACT_INPUT: Partial<Record<(typeof CONTACT_KEYS)[number], { type: string; inputMode?: 'tel' | 'email' | 'url' }>> = {
  phone: { type: 'tel', inputMode: 'tel' },
  email: { type: 'email', inputMode: 'email' },
  link: { type: 'url', inputMode: 'url' },
}

type ItemProps<T> = { id: string; value: T; onChange: (value: T) => void; label: string }

function ContactInput({ id, value, onChange, label }: ItemProps<Contact>) {
  return (
    <div className="grid grid-cols-2 gap-2" role="group" aria-label={label}>
      {CONTACT_KEYS.map((key) => (
        <Input
          key={key}
          id={key === 'name' ? id : undefined}
          placeholder={CONTACT_LABEL[key]}
          aria-label={CONTACT_LABEL[key]}
          type={CONTACT_INPUT[key]?.type}
          inputMode={CONTACT_INPUT[key]?.inputMode}
          value={value[key] ?? ''}
          onChange={(e) => onChange({ ...value, [key]: e.target.value })}
        />
      ))}
    </div>
  )
}

function LinkInput({ id, value, onChange, label }: ItemProps<LinkValue>) {
  return (
    <div className="flex gap-2" role="group" aria-label={label}>
      <Input
        placeholder={FIELDS_UI.linkTitle}
        aria-label={FIELDS_UI.linkTitle}
        className="w-1/3"
        value={value.title ?? ''}
        onChange={(e) => onChange({ ...value, title: e.target.value })}
      />
      <Input
        id={id}
        placeholder="https://…"
        aria-label={label}
        inputMode="url"
        value={value.url}
        onChange={(e) => onChange({ ...value, url: e.target.value })}
      />
    </div>
  )
}

function AreaRefSelect({ id, value, onChange, label, areas }: ItemProps<string> & { areas: Area[] }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? '' : v)}>
      <SelectTrigger id={id} className="w-full" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{FIELDS_UI.none}</SelectItem>
        {areas.map((a) => (
          <SelectItem key={a.id} value={a.id}>
            {a.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function emptyItem(def: FieldDef): unknown {
  if (def.type === 'contact') return {}
  if (def.type === 'link') return { title: '', url: '' }
  return ''
}

function SingleInput({ def, id, value, onChange, areas }: { def: FieldDef; id: string; value: unknown; onChange: (v: unknown) => void; areas: Area[] }) {
  switch (def.type) {
    case 'contact':
      return <ContactInput id={id} label={def.label} value={(value as Contact) ?? {}} onChange={onChange} />
    case 'link':
      return (
        <LinkInput
          id={id}
          label={def.label}
          value={typeof value === 'string' ? { url: value } : ((value as LinkValue) ?? { url: '' })}
          onChange={onChange}
        />
      )
    case 'area_ref':
      return <AreaRefSelect id={id} label={def.label} value={(value as string) ?? ''} onChange={onChange} areas={areas} />
    case 'number':
      return (
        <Input
          id={id}
          inputMode="decimal"
          className="w-40"
          value={value === undefined || value === null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'date':
      return <Input id={id} type="date" className="w-44" value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
    case 'select':
      return (
        <Select value={(value as string) || NONE} onValueChange={(v) => onChange(v === NONE ? null : v)}>
          <SelectTrigger id={id} className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{FIELDS_UI.none}</SelectItem>
            {def.options.map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    case 'multiselect':
      return (
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          className="flex-wrap"
          aria-label={def.label}
          value={Array.isArray(value) ? (value as string[]) : []}
          onValueChange={onChange}
        >
          {def.options.map((o) => (
            <ToggleGroupItem key={o} value={o}>
              {o}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )
    default:
      return <Input id={id} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
  }
}

function MultipleInput({ def, id, value, onChange, areas }: { def: FieldDef; id: string; value: unknown; onChange: (v: unknown) => void; areas: Area[] }) {
  const items: unknown[] = Array.isArray(value) ? value : value ? [value] : []
  const set = (i: number, item: unknown) => onChange(items.map((x, j) => (j === i ? item : x)))
  return (
    <FieldSet>
      <FieldLegend variant="label">
        {def.label}
        {def.required && ' *'}
      </FieldLegend>
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <SingleInput def={def} id={i === 0 ? id : `${id}-${i}`} value={item} onChange={(v) => set(i, v)} areas={areas} />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={FIELDS_UI.remove}
            onClick={() => onChange(items.filter((_, j) => j !== i))}
          >
            <XIcon />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...items, emptyItem(def)])}>
        <PlusIcon /> {FIELDS_UI.add}
      </Button>
    </FieldSet>
  )
}

/** Динамическая форма значений полей типа (FieldDef). Пустые значения сервер не хранит. */
export function FieldValuesForm({
  defs,
  value,
  onChange,
  areas = [],
  idPrefix = 'field',
}: {
  defs: FieldDef[]
  value: FieldValues
  onChange: (value: FieldValues) => void
  /** Для полей «сфера». */
  areas?: Area[]
  idPrefix?: string
}) {
  const set = (fieldId: string, v: unknown) => onChange({ ...value, [fieldId]: v })
  return (
    <>
      {defs.map((def) => {
        const id = `${idPrefix}-${def.id}`
        if (def.multiple) {
          return <MultipleInput key={def.id} def={def} id={id} value={value[def.id]} onChange={(v) => set(def.id, v)} areas={areas} />
        }
        if (def.type === 'bool') {
          return (
            <Field key={def.id} orientation="horizontal">
              <Switch id={id} checked={value[def.id] === true} onCheckedChange={(v) => set(def.id, v)} />
              <FieldLabel htmlFor={id}>{def.label}</FieldLabel>
            </Field>
          )
        }
        return (
          <Field key={def.id}>
            <FieldLabel htmlFor={id}>
              {def.label}
              {def.required && <span aria-label={FIELDS_UI.required}> *</span>}
            </FieldLabel>
            <SingleInput def={def} id={id} value={value[def.id]} onChange={(v) => set(def.id, v)} areas={areas} />
          </Field>
        )
      })}
    </>
  )
}
