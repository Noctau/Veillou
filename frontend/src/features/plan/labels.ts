import { formatDay, wallDate, wallTime } from '@/lib/time'

import type { PlanReason, PlanRevision, RiskReason } from './usePlan'

/** 1 блок, 2 блока, 5 блоков. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export const RISK_LABEL: Record<RiskReason, string> = {
  no_slots: 'нет подходящего времени до дедлайна',
  no_time: 'не хватает времени до дедлайна',
  dependency: 'не поставлен предыдущий шаг',
  late: 'позже, чем хотелось (впритык к дедлайну)',
  overdue: 'дедлайн уже прошёл',
  rest: 'влезет, только если отдать минимум отдыха',
}

export const REASON_LABEL: Record<PlanReason, string> = {
  manual: 'Перепланировали',
  changes: 'План устарел после правок',
  missed: 'Переносим невыполненное',
  nightly: 'Пересчитали план за ночь',
  weekly: 'Дела из ящика на неделю',
  exam: 'План подготовки к экзамену',
}

/** «3 блока перенесены · 1 задание под угрозой» */
export function summarize(rev: PlanRevision): string {
  const parts: string[] = []
  if (rev.moved) parts.push(`${rev.moved} ${plural(rev.moved, 'блок перенесён', 'блока перенесены', 'блоков перенесены')}`)
  if (rev.added) parts.push(`${rev.added} ${plural(rev.added, 'новый блок', 'новых блока', 'новых блоков')}`)
  if (rev.removed) parts.push(`${rev.removed} ${plural(rev.removed, 'блок убран', 'блока убраны', 'блоков убраны')}`)
  if (rev.missed) parts.push(`${rev.missed} ${plural(rev.missed, 'блок', 'блока', 'блоков')} в «не сделано»`)
  const risky = rev.at_risk.filter((r) => r.group_kind !== 'backlog')
  const tasks = new Set(risky.map((r) => r.group_id)).size
  if (tasks) parts.push(`${tasks} ${plural(tasks, 'задание', 'задания', 'заданий')} под угрозой`)
  const boxes = new Set(rev.at_risk.filter((r) => r.group_kind === 'backlog').map((r) => r.group_id)).size
  if (boxes) parts.push(`${boxes} ${plural(boxes, 'дело', 'дела', 'дел')} из ящика не влезает`)
  return parts.join(' · ')
}

/** «пн 7 окт., 10:00–11:30» */
export function slotText(slot: { start: string; end: string }, tz: string): string {
  return `${formatDay(wallDate(slot.start, tz))}, ${wallTime(slot.start, tz)}–${wallTime(slot.end, tz)}`
}
