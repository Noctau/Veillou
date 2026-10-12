/**
 * Показ значений пользовательских полей — как `render_values` в backend/app/domain/fields.py.
 * Значения приходят в формате хранения; «старые» (вариант убрали из списка) показываются как есть.
 */
import { FIELDS_UI } from '@/lib/terms'

import type { FieldDef, FieldDefIn, FieldType, FieldValues } from './useAreas'

export type Contact = Partial<Record<'name' | 'role' | 'phone' | 'email' | 'link' | 'note', string>>
export type LinkValue = { title?: string; url: string }

/** Поля, у которых бывает «несколько значений». */
export const MULTIPLE_TYPES = new Set(['text', 'contact', 'link', 'area_ref'])
export const CHOICE_TYPES = new Set(['select', 'multiselect'])

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

export function formatContact(c: Contact): string {
  let head = c.name ?? ''
  if (c.role) head = head ? `${head} (${c.role})` : c.role
  return [head, c.phone, c.email, c.link, c.note].filter(Boolean).join(' · ')
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

export function formatLink(l: LinkValue | string): string {
  if (typeof l === 'string') return l
  return l.title || hostname(l.url)
}

function formatDate(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : value
}

function formatOne(def: FieldDef, value: unknown, areaNames: Record<string, string>): string {
  switch (def.type) {
    case 'number':
      return String(value).replace('.', ',')
    case 'bool':
      return value ? FIELDS_UI.yes : FIELDS_UI.no
    case 'multiselect':
      return Array.isArray(value) ? value.join(', ') : String(value)
    case 'date':
      return formatDate(String(value))
    case 'contact':
      return typeof value === 'object' && value ? formatContact(value as Contact) : String(value)
    case 'link':
      return formatLink(value as LinkValue | string)
    case 'area_ref':
      return areaNames[String(value)] ?? ''
    default:
      return String(value)
  }
}

export type RenderedField = { def: FieldDef; text: string; value: unknown }

/** Подписи и тексты полей со значением — в порядке полей типа. */
export function renderFields(
  defs: FieldDef[],
  values: FieldValues | undefined,
  { onlyReminder = false, areaNames = {} }: { onlyReminder?: boolean; areaNames?: Record<string, string> } = {},
): RenderedField[] {
  const result: RenderedField[] = []
  for (const def of defs) {
    if (onlyReminder && !def.show_in_reminder) continue
    const value = values?.[def.id]
    if (isEmpty(value)) continue
    const items = def.multiple && Array.isArray(value) ? value : [value]
    const sep = def.type === 'contact' ? '; ' : ', '
    const text = items
      .map((v) => formatOne(def, v, areaNames))
      .filter(Boolean)
      .join(sep)
    if (text) result.push({ def, text, value })
  }
  return result
}

/** Пустые значения формы не отправляем: сервер их всё равно не хранит. */
export function compactValues(values: FieldValues): FieldValues {
  return Object.fromEntries(Object.entries(values).filter(([, v]) => !isEmpty(v)))
}

// ---------- черновик описания поля (редактор FieldDefsEditor) ----------

export type FieldDraft = {
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

export function toDraft(f?: FieldDef): FieldDraft {
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

export function fromDraft(d: FieldDraft): FieldDefIn {
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
