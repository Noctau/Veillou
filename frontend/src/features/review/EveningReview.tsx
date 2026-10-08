import { ArrowRightIcon, CheckCircle2Icon, ChevronDownIcon, ChevronUpIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { eventColor, timeRange } from '@/features/calendar/eventUtils'
import { type CalendarEvent, useUpdateEvent } from '@/features/calendar/useCalendar'
import { useAskFeel } from '@/features/plan/useAskFeel'
import { plural } from '@/features/plan/labels'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'
import { cn } from '@/lib/utils'

import { useEveningReview, useReschedule } from './useReview'

function Row({
  event,
  tz,
  done,
  busy,
  onDone,
  onMove,
}: {
  event: CalendarEvent
  tz: string
  done: boolean
  busy: boolean
  onDone: () => void
  onMove: () => void
}) {
  return (
    <li className={cn('flex items-center gap-3 rounded-lg px-2 py-2', done && 'opacity-60')}>
      <Checkbox aria-label="Сделано" className="size-5" checked={done} disabled={done || busy} onCheckedChange={onDone} />
      <span className={cn('h-8 w-1 shrink-0 rounded-full', paletteColor(eventColor(event)).bg)} />
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm font-medium', done && 'line-through')}>{event.title}</div>
        <div className="text-xs text-muted-foreground tabular-nums">{timeRange(event, tz)}</div>
      </div>
      {!done && (
        <Button size="sm" variant="ghost" disabled={busy} onClick={onMove}>
          Перенести
        </Button>
      )}
    </li>
  )
}

/**
 * Вечерний разбор (сценарий 3): одно касание — «перенести всё невыполненное»;
 * раскрыть — отметить сделанное и перенести по одному. Превью и угрозы дедлайнам —
 * в шторке плана, применяет пользователь.
 */
export function EveningReview() {
  const tz = useTimeZone()
  const { data, isPending, isError, error } = useEveningReview()
  const reschedule = useReschedule()
  const update = useUpdateEvent()
  const askFeel = useAskFeel()
  const [expanded, setExpanded] = useState(false)
  const [marked, setMarked] = useState<Set<string>>(new Set())

  if (isPending) return <Skeleton className="h-40" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  const left = data.items.filter((e) => !marked.has(e.id))
  const busy = reschedule.isPending

  const markDone = (e: CalendarEvent) => {
    setMarked((prev) => new Set(prev).add(e.id))
    update.mutate(
      { id: e.id, body: { status: 'done' } },
      {
        onSuccess: () => e.source_type === 'subtask' && e.source_id && askFeel(e.source_id),
        onError: () =>
          setMarked((prev) => {
            const next = new Set(prev)
            next.delete(e.id)
            return next
          }),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground first-letter:uppercase">
        {formatDay(data.date, { weekday: 'long', month: 'long' })}
        {data.done + marked.size > 0 && ` · сделано ${data.done + marked.size}`}
      </p>

      {left.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <CheckCircle2Icon className="size-8 text-emerald-500" />
            Всё отмечено — разбирать нечего.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <p className="text-sm">
              Не отмечено {left.length} {plural(left.length, 'блок', 'блока', 'блоков')}. Перенести — остальное сдвинется, а
              если дедлайн под угрозой, план предупредит.
            </p>
            <Button size="lg" disabled={busy} onClick={() => reschedule.mutate(left.map((e) => e.id))}>
              <ArrowRightIcon /> Перенести всё невыполненное
            </Button>
            <Button variant="ghost" size="sm" className="self-center" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
              По одному {expanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
            </Button>
            {expanded && (
              <ul className="flex flex-col">
                {data.items.map((e) => (
                  <Row
                    key={e.id}
                    event={e}
                    tz={tz}
                    done={marked.has(e.id)}
                    busy={busy}
                    onDone={() => markDone(e)}
                    onMove={() => reschedule.mutate([e.id])}
                  />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
