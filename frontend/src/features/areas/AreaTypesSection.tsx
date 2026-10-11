import { ArrowDownIcon, ArrowUpIcon, ChevronDownIcon, ChevronUpIcon, PlusIcon, Trash2Icon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { CategoryIcon } from '@/features/catalog/CategoryIcon'
import { IconPicker } from '@/features/catalog/IconPicker'
import type { CategoryIconName } from '@/features/catalog/useCatalog'
import { AREA_SECTION_LABEL, AREA_TYPES_UI as T, FIELD_TYPE_LABEL } from '@/lib/terms'

import { CHOICE_TYPES, MULTIPLE_TYPES } from './fields'
import {
  type AreaSection,
  type AreaType,
  type FieldDefIn,
  type FieldType,
  useAreaTypes,
  useCreateAreaType,
  useDeleteAreaType,
  useUpdateAreaType,
} from './useAreas'

const SECTIONS = Object.keys(AREA_SECTION_LABEL) as AreaSection[]
const FIELD_TYPES = Object.keys(FIELD_TYPE_LABEL) as FieldType[]
const DEFAULT_SECTIONS: AreaSection[] = ['schedule', 'tasks', 'notes']

type FieldDraft = {
  /** Нет — новое поле, id выдаст сервер. */
  id?: string
  key: string
  label: string
  type: FieldType
  options: string
  multiple: boolean
  required: boolean
  show_in_reminder: boolean
}

let draftSeq = 0

function toDraft(f?: AreaType['fields'][number]): FieldDraft {
  draftSeq += 1
  return {
    id: f?.id,
    key: f?.id ?? `new-${draftSeq}`,
    label: f?.label ?? '',
    type: f?.type ?? 'text',
    options: f?.options.join(', ') ?? '',
    multiple: f?.multiple ?? false,
    required: f?.required ?? false,
    show_in_reminder: f?.show_in_reminder ?? false,
  }
}

function fromDraft(d: FieldDraft): FieldDefIn {
  const choice = CHOICE_TYPES.has(d.type)
  return {
    id: d.id ?? null,
    label: d.label.trim(),
    type: d.type,
    options: choice
      ? d.options
          .split(',')
          .map((o) => o.trim())
          .filter(Boolean)
      : [],
    multiple: MULTIPLE_TYPES.has(d.type) && d.multiple,
    required: d.required,
    show_in_reminder: d.show_in_reminder,
  }
}

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

function FieldDefsEditor({ value, onChange }: { value: FieldDraft[]; onChange: (v: FieldDraft[]) => void }) {
  const move = (i: number, delta: -1 | 1) => {
    const next = [...value]
    ;[next[i], next[i + delta]] = [next[i + delta], next[i]]
    onChange(next)
  }
  return (
    <FieldSet>
      <FieldLegend variant="label">{T.fields}</FieldLegend>
      <FieldDescription>{T.fieldsHint}</FieldDescription>
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

function AreaTypeForm({ areaType, onDone }: { areaType?: AreaType; onDone: (created?: AreaType) => void }) {
  const create = useCreateAreaType()
  const update = useUpdateAreaType()
  const remove = useDeleteAreaType()
  const [name, setName] = useState(areaType?.name ?? '')
  const [plural, setPlural] = useState(areaType?.name_plural ?? '')
  const [icon, setIcon] = useState<CategoryIconName>(areaType?.icon ?? 'tag')
  const [color, setColor] = useState(areaType?.color ?? '#3b82f6')
  const [sections, setSections] = useState<AreaSection[]>(areaType?.sections ?? DEFAULT_SECTIONS)
  const [fields, setFields] = useState<FieldDraft[]>(() => areaType?.fields.map(toDraft) ?? [])
  const [more, setMore] = useState(false)
  const saving = create.isPending || update.isPending
  const valid =
    name.trim() !== '' &&
    plural.trim() !== '' &&
    fields.every((f) => f.label.trim() !== '' && (!CHOICE_TYPES.has(f.type) || (fromDraft(f).options ?? []).length > 0))

  const save = () => {
    const body = {
      name: name.trim(),
      name_plural: plural.trim(),
      icon,
      color,
      // Порядок разделов — как в списке
      sections: SECTIONS.filter((s) => sections.includes(s)),
      fields: fields.map(fromDraft),
    }
    if (areaType) update.mutate({ id: areaType.id, body }, { onSuccess: () => onDone() })
    else create.mutate(body, { onSuccess: (created) => onDone(created) })
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="aty-name">{T.name}</FieldLabel>
          <Input
            id="aty-name"
            autoFocus={!areaType}
            placeholder={T.namePlaceholder}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="aty-plural">{T.plural}</FieldLabel>
          <Input id="aty-plural" placeholder={T.pluralPlaceholder} value={plural} onChange={(e) => setPlural(e.target.value)} />
        </Field>
      </div>
      <FieldDefsEditor value={fields} onChange={setFields} />

      <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setMore((v) => !v)}>
        {more ? <ChevronUpIcon /> : <ChevronDownIcon />} {more ? T.less : T.more}
      </Button>
      {more && (
        <div className="flex flex-col gap-5">
          <Field>
            <FieldLabel>{T.sections}</FieldLabel>
            <ToggleGroup
              type="multiple"
              variant="outline"
              size="sm"
              className="flex-wrap"
              value={sections}
              onValueChange={(v) => setSections(v as AreaSection[])}
            >
              {SECTIONS.map((s) => (
                <ToggleGroupItem key={s} value={s}>
                  {AREA_SECTION_LABEL[s]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
          <Field>
            <FieldLabel>{T.icon}</FieldLabel>
            <IconPicker value={icon} onChange={setIcon} />
          </Field>
          <Field>
            <FieldLabel>{T.color}</FieldLabel>
            <ColorPicker value={color} onChange={setColor} />
          </Field>
        </div>
      )}

      <DialogFooter className="flex-row items-center">
        {areaType && (
          <ConfirmButton
            title={T.deleteTitle(areaType.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(areaType.id, { onSuccess: () => onDone() })}
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

/** Новый тип сферы или правка существующего. */
export function AreaTypeDialog({
  open,
  onOpenChange,
  areaType,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  areaType?: AreaType
  onCreated?: (areaType: AreaType) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{areaType?.name ?? T.newTitle}</DialogTitle>
        </DialogHeader>
        {open && (
          <AreaTypeForm
            key={areaType?.id ?? 'new'}
            areaType={areaType}
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

export function AreaTypesSection() {
  const { data: types, isPending } = useAreaTypes()
  const [editing, setEditing] = useState<{ areaType?: AreaType } | null>(null)

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
                onClick={() => setEditing({ areaType: t })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
              >
                <CategoryIcon name={t.icon} className="size-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{t.name_plural}</div>
                  {t.fields.length > 0 && (
                    <div className="truncate text-xs text-muted-foreground">{t.fields.map((f) => f.label).join(', ')}</div>
                  )}
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">{T.fieldsCount(t.fields.length)}</span>
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
      <AreaTypeDialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)} areaType={editing?.areaType} />
    </Card>
  )
}
