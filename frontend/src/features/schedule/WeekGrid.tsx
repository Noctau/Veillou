import { PlusIcon } from 'lucide-react'

import type { Subject } from '@/features/subjects/useSubjects'
import { paletteColor } from '@/lib/colors'
import { WEEKDAYS_SHORT } from '@/lib/time'
import { cn } from '@/lib/utils'

import { CLASS_TYPE_LABEL } from './parity'
import type { BellSlot, ClassRule, Parity } from './useSchedule'

type Props = {
  rules: ClassRule[]
  subjects: Map<string, Subject>
  bellsFor: (weekday: number) => BellSlot[]
  parity: Parity
  /** Дни недели, которые показываем (на телефоне — один). */
  weekdays: number[]
  onCreate: (weekday: number, pairNumber: number | null) => void
  onEdit: (rule: ClassRule) => void
}

// Литералы, чтобы Tailwind их увидел
const COLS: Record<number, string> = {
  1: 'grid-cols-[4rem_1fr]',
  6: 'grid-cols-[4rem_repeat(6,minmax(0,1fr))]',
  7: 'grid-cols-[4rem_repeat(7,minmax(0,1fr))]',
}

function visible(rule: ClassRule, parity: Parity) {
  return rule.parity === 'all' || rule.parity === parity
}

function RuleChip({ rule, subject, onClick }: { rule: ClassRule; subject?: Subject; onClick: () => void }) {
  const color = paletteColor(subject?.color)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full flex-col gap-0.5 rounded-md border-l-4 px-2 py-1.5 text-left text-xs transition hover:brightness-125',
        color.border,
        color.soft,
      )}
    >
      <span className="line-clamp-2 font-medium leading-tight text-foreground">
        {subject?.short_name || subject?.name || '—'}
      </span>
      <span className="text-muted-foreground">
        {CLASS_TYPE_LABEL[rule.class_type]}
        {rule.location && ` · ${rule.location}`}
        {rule.start_time && ` · ${rule.start_time}–${rule.end_time}`}
      </span>
      {rule.parity !== 'all' && (
        <span className="text-[10px] tracking-wide text-muted-foreground uppercase">
          {rule.parity === 'odd' ? 'числ.' : 'знам.'}
        </span>
      )}
    </button>
  )
}

function EmptyCell({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  if (disabled) return <div className="h-full min-h-12 rounded-md bg-muted/30" />
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Добавить пару"
      className="flex h-full min-h-12 w-full items-center justify-center rounded-md border border-dashed border-border/40 text-muted-foreground/30 transition hover:border-border hover:text-muted-foreground focus-visible:border-border focus-visible:text-muted-foreground"
    >
      <PlusIcon className="size-4" />
    </button>
  )
}

/** Сетка «дни × номер пары» для выбранной чётности. */
export function WeekGrid({ rules, subjects, bellsFor, parity, weekdays, onCreate, onEdit }: Props) {
  const numbers = [...new Set(weekdays.flatMap((wd) => bellsFor(wd).map((s) => s.number)))].sort((a, b) => a - b)
  // Время пары в заголовке строки — по первому показанному дню, где эта пара есть
  const rowTime = (n: number) => {
    for (const wd of weekdays) {
      const slot = bellsFor(wd).find((s) => s.number === n)
      if (slot) return slot
    }
  }
  const shown = rules.filter((r) => visible(r, parity))
  const custom = shown.filter((r) => r.start_time)
  const single = weekdays.length === 1

  const cell = (wd: number, n: number) => {
    const here = shown.filter((r) => r.weekday === wd && !r.start_time && r.pair_number === n)
    const hasSlot = bellsFor(wd).some((s) => s.number === n)
    return (
      <div key={`${wd}-${n}`} className="flex flex-col gap-1">
        {here.map((r) => (
          <RuleChip key={r.id} rule={r} subject={subjects.get(r.subject_id)} onClick={() => onEdit(r)} />
        ))}
        {here.length === 0 && <EmptyCell disabled={!hasSlot} onClick={() => onCreate(wd, n)} />}
      </div>
    )
  }

  return (
    <div className={cn('grid gap-1.5', COLS[weekdays.length] ?? COLS[6], !single && 'min-w-[640px]')}>
      {!single && (
        <>
          <div />
          {weekdays.map((wd) => (
            <div key={wd} className="pb-1 text-center text-sm font-medium text-muted-foreground">
              {WEEKDAYS_SHORT[wd - 1]}
            </div>
          ))}
        </>
      )}
      {numbers.map((n) => {
        const slot = rowTime(n)
        return (
          <div key={n} className="contents">
            <div className="flex flex-col pt-1 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{n}</span>
              {slot && (
                <span>
                  {slot.start}
                  <br />
                  {slot.end}
                </span>
              )}
            </div>
            {weekdays.map((wd) => cell(wd, n))}
          </div>
        )
      })}
      {custom.length > 0 && (
        <div className="contents">
          <div className="pt-1 text-xs text-muted-foreground">Своё время</div>
          {weekdays.map((wd) => (
            <div key={wd} className="flex flex-col gap-1">
              {custom
                .filter((r) => r.weekday === wd)
                .map((r) => (
                  <RuleChip key={r.id} rule={r} subject={subjects.get(r.subject_id)} onClick={() => onEdit(r)} />
                ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
