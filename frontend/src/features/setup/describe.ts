import { SETUP_UI as T } from '@/lib/terms'
import { WEEKDAYS_SHORT } from '@/lib/time'

import type { Bundle } from './useSetup'

export type Section = Exclude<keyof Bundle, 'version' | 'settings'>
type Item = { ref: string } & Record<string, unknown>

/** Разделы черновика в порядке показа (кирпичи, которые чаще правят, — выше). */
export const SECTIONS: Section[] = [
  'event_types',
  'schedule_rules',
  'area_types',
  'areas',
  'day_profiles',
  'day_profile_rules',
  'budgets',
  'task_types',
  'periods',
  'days_off',
  'slot_grids',
  'categories',
  'action_types',
  'event_rules',
]

function hours(minutes: number) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return [h ? `${h} ч` : '', m ? `${m} мин` : ''].filter(Boolean).join(' ')
}

function days(list: number[]) {
  return list.map((d) => WEEKDAYS_SHORT[d - 1]).join(', ')
}

type Pattern = { kind: string; weekdays?: number[]; on?: number; off?: number; anchor?: string; date?: string; rrule?: string }

function pattern(p: Pattern) {
  if (p.kind === 'weekly') return days(p.weekdays ?? [])
  if (p.kind === 'day_cycle') return T.shifts(p.on ?? 0, p.off ?? 0, p.anchor ?? '')
  if (p.kind === 'once') return p.date ?? ''
  return p.rrule ?? ''
}

/** Заголовок кирпича: название или ref. */
export function itemTitle(item: Item) {
  return String(item.name ?? item.title_template ?? item.title ?? item.ref)
}

/** Короткая строка-описание кирпича под заголовком. */
export function itemSummary(section: Section, raw: Item): string {
  const item = raw as unknown as Record<string, never>
  switch (section) {
    case 'event_types': {
      const parts = []
      if (item.buffer_before_min) parts.push(T.travel(item.buffer_before_min))
      if (item.remind_before_min) parts.push(T.remind(item.remind_before_min))
      if (item.is_rest) parts.push(T.rest)
      return parts.join(' · ')
    }
    case 'schedule_rules': {
      const time = item.start_time ? `${item.start_time}–${item.end_time}` : T.slots(item.slot_from, item.slot_to)
      return [item.event_type, item.area, pattern(item.pattern), time].filter(Boolean).join(' · ')
    }
    case 'areas':
      return item.area_type
    case 'area_types':
      return (item.fields as { label: string }[]).map((f) => f.label).join(', ')
    case 'day_profiles': {
      const windows = (item.work_windows as { start: string; end: string }[]).map((w) => `${w.start}–${w.end}`)
      return [T.wake(item.wake), T.sleep(item.sleep), windows.length ? T.work(windows.join(', ')) : '']
        .filter(Boolean)
        .join(' · ')
    }
    case 'day_profile_rules':
      return `${item.profile}: ${T.ruleKind(item.kind, item.event_type, days(item.weekdays ?? []), item.date_from)}`
    case 'budgets':
      return [hours(item.minutes_per_day), ...(item.event_types as string[]), ...(item.action_types as string[])].join(' · ')
    case 'task_types':
    case 'action_types':
      return (item.synonyms as string[]).join(', ')
    case 'periods':
      return `${item.start_date} — ${item.end_date}`
    case 'days_off':
      return `${item.date_from} — ${item.date_to}`
    default:
      return ''
  }
}

/** Ссылки кирпича на другие разделы — чтобы удалять зависимых вместе с ним. */
const REFS: Partial<Record<Section, Record<string, Section>>> = {
  action_types: { category: 'categories' },
  task_types: { action_type: 'action_types', category: 'categories' },
  days_off: { period: 'periods' },
  slot_grids: { period: 'periods' },
  areas: { area_type: 'area_types', period: 'periods' },
  event_types: { default_area_type: 'area_types' },
  budgets: { action_types: 'action_types', event_types: 'event_types' },
  day_profile_rules: { profile: 'day_profiles', event_type: 'event_types' },
  schedule_rules: { event_type: 'event_types', area: 'areas', period: 'periods', slot_grid: 'slot_grids' },
  event_rules: { event_type: 'event_types', schedule_rule: 'schedule_rules', action_type: 'action_types', task_type: 'task_types' },
}

/** Сборка без кирпича: необязательные ссылки на него обнуляются, списки чистятся,
 *  кирпичи с обязательной ссылкой уходят следом. */
export function removeItem(bundle: Bundle, section: Section, ref: string): Bundle {
  const gone: [Section, string][] = [[section, ref]]
  let next = { ...bundle } as Record<string, unknown>
  while (gone.length) {
    const [s, r] = gone.pop()!
    next[s] = (next[s] as Item[]).filter((i) => i.ref !== r)
    for (const [other, refs] of Object.entries(REFS) as [Section, Record<string, Section>][]) {
      next[other] = (next[other] as Item[]).flatMap((item) => {
        let changed = item
        for (const [field, target] of Object.entries(refs)) {
          if (target !== s) continue
          const value = item[field]
          if (Array.isArray(value)) changed = { ...changed, [field]: value.filter((v) => v !== r) }
          else if (value === r) {
            if (REQUIRED.has(`${other}.${field}`)) {
              gone.push([other, item.ref])
              return [item]
            }
            changed = { ...changed, [field]: null }
          }
        }
        return [changed]
      })
    }
    if (s === 'action_types' && (next.settings as { default_action_type?: string }).default_action_type === r) {
      next = { ...next, settings: { default_action_type: null } }
    }
  }
  return next as Bundle
}

const REQUIRED = new Set([
  'areas.area_type',
  'day_profile_rules.profile',
  'day_profile_rules.event_type',
  'schedule_rules.event_type',
  'event_rules.event_type',
  'event_rules.schedule_rule',
])

/** «Заново с комментарием»: прошлый черновик кратко, строками. */
export function previousLines(bundle: Bundle): string[] {
  return SECTIONS.flatMap((s) =>
    (bundle[s] as Item[]).map((i) => `${T.section[s]}: ${itemTitle(i)} — ${itemSummary(s, i)}`.slice(0, 300)),
  ).slice(0, 60)
}
