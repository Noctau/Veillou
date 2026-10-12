import { PlusIcon } from 'lucide-react'

import { renderFields } from '@/features/areas/fields'
import type { Area } from '@/features/areas/useAreas'
import { paletteColor } from '@/lib/colors'
import { SCHEDULE_UI as T } from '@/lib/terms'
import { WEEKDAYS_SHORT } from '@/lib/time'
import { cn } from '@/lib/utils'

import { minutes, onWeekCell, ruleLabel } from './pattern'
import type { EventType, ScheduleRule, Slot } from './useSchedule'

type Props = {
  rules: ScheduleRule[]
  areas: Map<string, Area>
  types: Map<string, EventType>
  /** Слоты дня недели; пусто — сетки нет, строки — шкала времени. */
  slotsFor: (weekday: number) => Slot[]
  cycleWeek: number
  /** Дни недели, которые показываем (на телефоне — один). */
  weekdays: number[]
  onCreate: (weekday: number, slot: number | null) => void
  onEdit: (rule: ScheduleRule) => void
}

// Литералы, чтобы Tailwind их увидел
const COLS: Record<number, string> = {
  1: 'grid-cols-[4rem_1fr]',
  5: 'grid-cols-[4rem_repeat(5,minmax(0,1fr))]',
  6: 'grid-cols-[4rem_repeat(6,minmax(0,1fr))]',
  7: 'grid-cols-[4rem_repeat(7,minmax(0,1fr))]',
}


function RuleChip({
  rule,
  area,
  type,
  showTime,
  onClick,
}: {
  rule: ScheduleRule
  area?: Area
  type?: EventType
  showTime: boolean
  onClick: () => void
}) {
  const color = paletteColor(rule.color ?? area?.color ?? type?.color)
  const inline = type ? renderFields(type.fields, rule.fields, { onlyReminder: true }).filter((f) => f.def.type === 'select' || f.def.type === 'multiselect') : []
  const details = [
    ...inline.map((f) => f.text),
    rule.location,
    showTime && rule.start_time && `${rule.start_time}–${rule.end_time}`,
  ].filter(Boolean)
  const weeks = rule.pattern.kind === 'weekly' ? rule.pattern.cycle_weeks : null
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
      <span className="line-clamp-2 font-medium leading-tight text-foreground">{ruleLabel(rule, area, type)}</span>
      {details.length > 0 && <span className="text-muted-foreground">{details.join(' · ')}</span>}
      {!!weeks?.length && (
        <span className="text-[10px] tracking-wide text-muted-foreground uppercase">
          {weeks.map(T.cycleWeek).join(', ')}
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
      aria-label={T.addRuleCell}
      className="flex h-full min-h-12 w-full items-center justify-center rounded-md border border-dashed border-border/40 text-muted-foreground/30 transition hover:border-border hover:text-muted-foreground focus-visible:border-border focus-visible:text-muted-foreground"
    >
      <PlusIcon className="size-4" />
    </button>
  )
}

/**
 * Неделя цикла: строки — слоты сетки (если она есть), иначе шкала времени
 * (правила дня по началу). Правила не «по дням недели» — отдельным списком у экрана.
 */
export function WeekGrid({ rules, areas, types, slotsFor, cycleWeek, weekdays, onCreate, onEdit }: Props) {
  const numbers = [...new Set(weekdays.flatMap((wd) => slotsFor(wd).map((s) => s.number)))].sort((a, b) => a - b)
  const bySlots = numbers.length > 0
  const shown = rules.filter((r) => r.pattern.kind === 'weekly')
  const at = (wd: number) => shown.filter((r) => onWeekCell(r, wd, cycleWeek))
  const single = weekdays.length === 1
  const chip = (r: ScheduleRule, showTime: boolean) => (
    <RuleChip
      key={r.id}
      rule={r}
      area={r.area_id ? areas.get(r.area_id) : undefined}
      type={types.get(r.event_type_id)}
      showTime={showTime}
      onClick={() => onEdit(r)}
    />
  )
  // Время слота в заголовке строки — по первому показанному дню, где он есть
  const rowTime = (n: number) => {
    for (const wd of weekdays) {
      const slot = slotsFor(wd).find((s) => s.number === n)
      if (slot) return slot
    }
  }
  const timed = (wd: number) =>
    at(wd)
      .filter((r) => r.start_time)
      .sort((a, b) => minutes(a.start_time!) - minutes(b.start_time!))

  return (
    <div className={cn('grid gap-1.5', COLS[weekdays.length] ?? COLS[7], !single && 'min-w-[640px]')}>
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
      {bySlots &&
        numbers.map((n) => {
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
              {weekdays.map((wd) => {
                const here = at(wd).filter((r) => !r.start_time && r.slot_from === n)
                const hasSlot = slotsFor(wd).some((s) => s.number === n)
                return (
                  <div key={`${wd}-${n}`} className="flex flex-col gap-1">
                    {here.map((r) => chip(r, false))}
                    {here.length === 0 && <EmptyCell disabled={!hasSlot} onClick={() => onCreate(wd, n)} />}
                  </div>
                )
              })}
            </div>
          )
        })}
      <div className="contents">
        <div className="pt-1 text-xs text-muted-foreground">{bySlots ? T.ownTime : T.time}</div>
        {weekdays.map((wd) => (
          <div key={wd} className="flex flex-col gap-1">
            {timed(wd).map((r) => chip(r, true))}
            {!bySlots && <EmptyCell onClick={() => onCreate(wd, null)} />}
          </div>
        ))}
      </div>
    </div>
  )
}
