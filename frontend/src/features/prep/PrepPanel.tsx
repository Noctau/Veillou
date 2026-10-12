import {
  CalendarRangeIcon,
  CheckIcon,
  CircleIcon,
  ClipboardCheckIcon,
  ListPlusIcon,
  MapPinIcon,
  PencilIcon,
  PlusIcon,
  RotateCwIcon,
  XIcon,
} from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { formatMinutes } from '@/features/tasks/labels'
import { errorMessage } from '@/lib/errors'
import { PREP_UI as T } from '@/lib/terms'
import { formatDay, todayIn, wallDate, wallTime } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'
import { cn } from '@/lib/utils'

import { PrepDialog } from './PrepDialog'
import {
  type PlanFilter,
  type PrepItem,
  type PrepItemStatus,
  type PrepPlanDetail,
  type PrepSession,
  useImportItems,
  usePrepEnable,
  usePrepPlan,
  usePrepPlans,
  useUpdateItem,
} from './usePrep'

const STATUS: Record<PrepItemStatus, { next: PrepItemStatus; icon: typeof CheckIcon; tone: string }> = {
  not_started: { next: 'learned', icon: CircleIcon, tone: 'text-muted-foreground' },
  learned: { next: 'review', icon: CheckIcon, tone: 'text-emerald-600 dark:text-emerald-400' },
  review: { next: 'not_started', icon: RotateCwIcon, tone: 'text-amber-600 dark:text-amber-400' },
}

function daysLeft(target: string, tz: string): number {
  return Math.round((Date.parse(wallDate(target, tz)) - Date.parse(todayIn(tz))) / 86_400_000)
}

/** Вставка списком: «1. …», «1) …» или по одному в строке. */
function ImportItems({ planId, onDone }: { planId: string; onDone?: () => void }) {
  const [text, setText] = useState('')
  const importItems = useImportItems()
  return (
    <div className="flex flex-col gap-2">
      <Textarea
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={T.itemsPlaceholder}
        aria-label={T.itemsLabel}
      />
      <div className="flex justify-end gap-2">
        {onDone && (
          <Button variant="ghost" size="sm" onClick={onDone}>
            {T.cancel}
          </Button>
        )}
        <Button
          size="sm"
          disabled={!text.trim() || importItems.isPending}
          onClick={() =>
            importItems.mutate(
              { id: planId, text },
              {
                onSuccess: () => {
                  setText('')
                  onDone?.()
                },
              },
            )
          }
        >
          <ListPlusIcon /> {T.addItems}
        </Button>
      </div>
    </div>
  )
}

function ItemRow({ item, planId }: { item: PrepItem; planId: string }) {
  const update = useUpdateItem(planId)
  const s = STATUS[item.status]
  const Icon = s.icon
  return (
    <li className="flex items-start gap-2 py-1.5">
      <span className="w-7 shrink-0 pt-0.5 text-right text-sm text-muted-foreground tabular-nums">{item.number}.</span>
      <span className="min-w-0 flex-1 text-sm">{item.text}</span>
      <Button
        variant="ghost"
        size="sm"
        className={cn('shrink-0 gap-1 px-2', s.tone)}
        aria-label={T.statusLabel(T.status[item.status], T.status[s.next])}
        onClick={() => update.mutate({ id: item.id, status: s.next })}
      >
        <Icon className="size-4" />
        <span className="text-xs">{T.status[item.status]}</span>
      </Button>
    </li>
  )
}

function Items({ plan }: { plan: PrepPlanDetail }) {
  const [adding, setAdding] = useState(false)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{T.items}</CardTitle>
        {plan.items.length > 0 && (
          <CardAction>
            <Button variant="ghost" size="sm" onClick={() => setAdding(true)}>
              <PlusIcon /> {T.more}
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {plan.items.length === 0 ? (
          <>
            <p className="text-sm text-muted-foreground">{T.itemsHint}</p>
            <ImportItems planId={plan.id} />
          </>
        ) : (
          <>
            {adding && <ImportItems planId={plan.id} onDone={() => setAdding(false)} />}
            <p className="text-xs text-muted-foreground">{T.statusHint}</p>
            <ul className="flex flex-col divide-y">
              {plan.items.map((q) => (
                <ItemRow key={q.id} item={q} planId={plan.id} />
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Days({ plan }: { plan: PrepPlanDetail }) {
  const tz = useTimeZone()
  const enable = usePrepEnable()
  const byDay = new Map<string, PrepSession[]>()
  for (const s of plan.sessions) byDay.set(s.date, [...(byDay.get(s.date) ?? []), s])

  if (!plan.enabled) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <p className="text-sm text-muted-foreground">
            {T.buildHint(plan.start_days_before, T.strategyHints[plan.strategy])}
          </p>
          <Button
            disabled={!plan.items.length || !plan.target || enable.isPending}
            onClick={() => enable.mutate({ id: plan.id, enable: true })}
          >
            <CalendarRangeIcon /> {T.build}
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{T.plan}</CardTitle>
        <CardAction>
          <ConfirmButton
            title={T.removeTitle}
            description={T.removeDescription}
            confirmLabel={T.remove}
            onConfirm={() => enable.mutate({ id: plan.id, enable: false })}
          >
            <Button variant="ghost" size="sm">
              <XIcon /> {T.remove}
            </Button>
          </ConfirmButton>
        </CardAction>
      </CardHeader>
      <CardContent>
        {byDay.size === 0 ? (
          <p className="text-sm text-muted-foreground">{T.nothingLeft}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {[...byDay.entries()].map(([day, sessions]) => (
              <li key={day} className="flex flex-col gap-1">
                <div className="text-sm font-medium first-letter:uppercase">{formatDay(day, { weekday: 'short' })}</div>
                {sessions.map((s) => (
                  <div key={s.id} className={cn('flex items-baseline gap-2 text-sm', s.status !== 'planned' && 'opacity-60')}>
                    <span className="min-w-0 flex-1">
                      <span className={cn(s.status === 'done' && 'line-through')}>{T.sessionKind[s.kind]}</span>
                      {s.kind !== 'run' && <span className="text-muted-foreground"> №{s.numbers.join(', ')}</span>}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                      {s.status === 'done'
                        ? T.done
                        : s.status === 'missed'
                          ? T.missed
                          : s.start && s.end
                            ? `${wallTime(s.start, tz)}–${wallTime(s.end, tz)}`
                            : formatMinutes(s.minutes)}
                    </span>
                  </div>
                ))}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function PlanView({ planId, areaId }: { planId: string; areaId?: string }) {
  const tz = useTimeZone()
  const { data: plan, isPending, isError, error } = usePrepPlan(planId)
  const [editing, setEditing] = useState(false)
  if (isPending) return <Skeleton className="h-48" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  const left = plan.target ? daysLeft(plan.target, tz) : null
  const total = plan.items_total
  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{plan.title}</CardTitle>
          <CardAction>
            <Button variant="ghost" size="icon" aria-label={T.edit} onClick={() => setEditing(true)}>
              <PencilIcon />
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {plan.target ? (
              <span className="first-letter:uppercase">
                {formatDay(wallDate(plan.target, tz), { weekday: 'short', month: 'long' })}
                {plan.event && `, ${wallTime(plan.target, tz)}`}
              </span>
            ) : (
              <Badge variant="outline">{T.noTarget}</Badge>
            )}
            {plan.event?.location && (
              <span className="flex items-center gap-1">
                <MapPinIcon className="size-3.5" />
                {plan.event.location}
              </span>
            )}
            {left !== null && left > 0 && <Badge variant="secondary">{T.inDays(left)}</Badge>}
            {left === 0 && <Badge>{T.today}</Badge>}
            {left !== null && left < 0 && <Badge variant="outline">{T.past}</Badge>}
          </div>
          {total > 0 && (
            <div className="flex items-center gap-3">
              <Progress value={(plan.items_learned / total) * 100} className="h-2 flex-1" aria-label={T.progress} />
              <span className="text-xs text-muted-foreground tabular-nums">{T.of(plan.items_learned, total)}</span>
            </div>
          )}
        </CardContent>
      </Card>
      <Days plan={plan} />
      <Items plan={plan} />
      <PrepDialog areaId={areaId} plan={plan} open={editing} onOpenChange={setEditing} />
    </div>
  )
}

/** «Подготовка» сферы или события (M20.2): цель, пункты со статусами, план по дням. */
export function PrepPanel({ areaId, eventId, emptyHint }: { areaId?: string; eventId?: string; emptyHint?: string }) {
  const filter: PlanFilter = eventId ? { event_id: eventId } : areaId ? { area_id: areaId } : {}
  const { data: plans, isPending, isError, error } = usePrepPlans(filter)
  const [creating, setCreating] = useState(false)
  if (isPending) return <Skeleton className="h-32" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  return (
    <div className="flex flex-col gap-4">
      {plans.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
          <ClipboardCheckIcon className="size-8" />
          {emptyHint && <p className="text-foreground">{emptyHint}</p>}
          <p>{T.empty}</p>
          <Button className="mt-2" onClick={() => setCreating(true)}>
            <PlusIcon /> {T.add}
          </Button>
        </div>
      ) : (
        <>
          {plans.map((p) => (
            <PlanView key={p.id} planId={p.id} areaId={areaId} />
          ))}
          {!eventId && (
            <Button variant="ghost" size="sm" className="self-start" onClick={() => setCreating(true)}>
              <PlusIcon /> {T.addMore}
            </Button>
          )}
        </>
      )}
      <PrepDialog areaId={areaId} eventId={eventId} open={creating} onOpenChange={setCreating} />
    </div>
  )
}
