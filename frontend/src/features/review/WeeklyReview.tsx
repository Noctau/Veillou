import { CalendarCheckIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { ageLabel, estimateLabel } from '@/features/backlog/labels'
import { type BacklogItem, useBacklog } from '@/features/backlog/useBacklog'
import { plural } from '@/features/plan/labels'
import { formatMinutes } from '@/features/tasks/labels'
import { errorMessage } from '@/lib/errors'
import { addDaysIso, formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { useConfirmWeek, useWeeklyReview, type WeeklyReview as Review } from './useReview'

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="flex flex-col rounded-lg bg-muted px-3 py-2">
      <span className="text-lg font-semibold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  )
}

function Stats({ review }: { review: Review }) {
  const s = review.stats
  const end = addDaysIso(s.week_start, 6)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Итоги: {formatDay(s.week_start, { weekday: undefined })} — {formatDay(end, { weekday: undefined })}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat value={`${s.blocks_done} из ${s.blocks_planned}`} label="блоков сделано" />
        <Stat value={s.done_minutes ? formatMinutes(s.done_minutes) : '—'} label="по плану" />
        <Stat value={s.tasks_done} label={plural(s.tasks_done, 'задание сдано', 'задания сдано', 'заданий сдано')} />
        <Stat value={s.backlog_done} label="дел из ящика" />
      </CardContent>
    </Card>
  )
}

function ItemRow({
  item,
  checked,
  disabled,
  onToggle,
  hint,
}: {
  item: BacklogItem
  checked: boolean
  disabled: boolean
  onToggle: () => void
  hint?: string
}) {
  const estimate = estimateLabel(item.estimate_min)
  return (
    <li>
      <label className={cn('flex items-center gap-3 rounded-lg px-2 py-2', disabled && !checked && 'opacity-50')}>
        <Checkbox className="size-5" checked={checked} disabled={disabled && !checked} onCheckedChange={onToggle} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{item.title}</span>
          <span className="block text-xs text-muted-foreground">
            {[hint, estimate, item.desired_by && `до ${formatDay(item.desired_by, { weekday: undefined })}`]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{ageLabel(item.created_at)}</span>
      </label>
    </li>
  )
}

function Picker({ review }: { review: Review }) {
  const { data: active } = useBacklog('active')
  const confirm = useConfirmWeek()
  const initial = [...review.planned, ...review.suggestions].map((i) => i.id)
  const [selected, setSelected] = useState<string[]>(initial)
  const [showAll, setShowAll] = useState(false)

  const shown = new Set(initial)
  const others = (active ?? []).filter((i) => !shown.has(i.id))
  const full = selected.length >= review.per_week
  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  const changed = selected.length !== initial.length || selected.some((id) => !review.planned.some((p) => p.id === id))

  const row = (item: BacklogItem, hint?: string) => (
    <ItemRow
      key={item.id}
      item={item}
      hint={hint}
      checked={selected.includes(item.id)}
      disabled={full}
      onToggle={() => toggle(item.id)}
    />
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Из ящика на неделю с {formatDay(review.week_start, { weekday: undefined })}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          До {review.per_week} {plural(review.per_week, 'дела', 'дел', 'дел')}: встанут в свободные окна после учёбы, с учётом
          условий.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {review.planned.length + review.suggestions.length === 0 && !others.length ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Ящик пуст.</p>
        ) : (
          <ul className="flex flex-col">
            {review.planned.map((i) => row(i, 'уже на неделе'))}
            {review.suggestions.map((i) => row(i))}
            {showAll && others.map((i) => row(i))}
          </ul>
        )}
        {!showAll && others.length > 0 && (
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setShowAll(true)}>
            Выбрать другое ({others.length})
          </Button>
        )}
        <Button disabled={confirm.isPending || (!changed && review.planned.length > 0)} onClick={() => confirm.mutate(selected)}>
          <CalendarCheckIcon /> {selected.length ? `Поставить в план: ${selected.length}` : 'Ничего не брать'}
        </Button>
      </CardContent>
    </Card>
  )
}

/** Недельный разбор (сценарий 6): итоги и 1–N дел из ящика → подтверждение → превью плана. */
export function WeeklyReview() {
  const { data, isPending, isError, error } = useWeeklyReview()
  if (isPending) return <Skeleton className="h-64" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  return (
    <div className="flex flex-col gap-4">
      <Stats review={data} />
      <Picker key={data.week_start + data.planned.map((i) => i.id).join()} review={data} />
    </div>
  )
}
