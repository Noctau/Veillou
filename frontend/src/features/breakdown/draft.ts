import { arrayMove } from '@dnd-kit/sortable'

import { formatMinutes } from '@/features/tasks/labels'

import type { BreakdownStep } from './useBreakdown'

/**
 * Шаг на экране проверки. Зависимости — ключи шагов выше (не индексы): так
 * перетаскивание и удаление их не путают. На сервер уходят индексы.
 */
export type DraftStep = {
  key: string
  title: string
  estimate_min: number
  action_type_id: string | null
  depends_on: string[]
  note: string
}

export const MIN_STEP = 5
export const MAX_STEP = 600

export function newKey(): string {
  return crypto.randomUUID()
}

export function fromSteps(steps: BreakdownStep[]): DraftStep[] {
  const keys = steps.map(() => newKey())
  return steps.map((s, i) => ({
    key: keys[i],
    title: s.title,
    estimate_min: s.estimate_min,
    action_type_id: s.action_type_id ?? null,
    depends_on: (s.depends_on ?? []).filter((d) => d >= 0 && d < i).map((d) => keys[d]),
    note: s.note ?? '',
  }))
}

export function toSteps(draft: DraftStep[]): BreakdownStep[] {
  const index = new Map(draft.map((s, i) => [s.key, i]))
  return draft.map((s, i) => ({
    title: s.title.trim(),
    estimate_min: s.estimate_min,
    action_type_id: s.action_type_id,
    depends_on: s.depends_on.map((k) => index.get(k)).filter((d): d is number => d !== undefined && d < i),
    note: s.note,
  }))
}

/** Зависеть можно только от шагов выше — так циклов не бывает. */
function keepEarlierDeps(draft: DraftStep[]): DraftStep[] {
  const seen = new Set<string>()
  return draft.map((s) => {
    const deps = s.depends_on.filter((k) => seen.has(k))
    seen.add(s.key)
    return deps.length === s.depends_on.length ? s : { ...s, depends_on: deps }
  })
}

export function moveStep(draft: DraftStep[], from: number, to: number): DraftStep[] {
  return keepEarlierDeps(arrayMove(draft, from, to))
}

export function removeStep(draft: DraftStep[], key: string): DraftStep[] {
  return draft.filter((s) => s.key !== key).map((s) => ({ ...s, depends_on: s.depends_on.filter((k) => k !== key) }))
}

export function validStep(s: DraftStep): boolean {
  return s.title.trim() !== '' && Number.isInteger(s.estimate_min) && s.estimate_min >= MIN_STEP && s.estimate_min <= MAX_STEP
}

export function totalMinutes(draft: DraftStep[]): number {
  return draft.reduce((sum, s) => sum + (Number.isFinite(s.estimate_min) ? s.estimate_min : 0), 0)
}

/** Как `domain/breakdown.time_warning` на сервере — пересчитывается при правке оценок. */
export function timeWarning(total: number, free: number | null, coef: number): string | null {
  if (free === null || total <= 0) return null
  const need = Math.round(total * coef)
  if (free <= 0) return 'До дедлайна свободного времени не осталось'
  if (need > free) return `Нужно ~${formatMinutes(need)}, а до дедлайна свободно ~${formatMinutes(free)} — не всё успеется`
  if (need * 1.25 > free) return `Впритык: нужно ~${formatMinutes(need)} из ~${formatMinutes(free)} свободных`
  return null
}
