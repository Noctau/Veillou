import { PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDay } from '@/lib/time'
import { SCHEDULE_UI as T } from '@/lib/terms'

import { useCreateDayOff, useDaysOff, useDeleteDayOff } from './useSchedule'

/**
 * Исключения периода: дни без правил периода (праздники, практика). Без периода —
 * во всех периодах. Правила без периода исключения не трогают.
 */
export function DaysOffEditor({ periodId }: { periodId?: string }) {
  const { data = [] } = useDaysOff()
  const create = useCreateDayOff()
  const remove = useDeleteDayOff()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [title, setTitle] = useState('')
  // Свои исключения периода и общие (они тоже действуют в периоде)
  const daysOff = data.filter((d) => !d.period_id || d.period_id === periodId)

  const add = () =>
    create.mutate(
      { period_id: periodId ?? null, date_from: from, date_to: to || from, title },
      {
        onSuccess: () => {
          setFrom('')
          setTo('')
          setTitle('')
        },
      },
    )

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">{T.daysOffHint}</p>
      {daysOff.length === 0 && <p className="text-sm text-muted-foreground">{T.noDaysOff}</p>}
      <ul className="flex flex-col gap-1">
        {daysOff.map((d) => (
          <li key={d.id} className="flex items-center gap-2 text-sm">
            <span className="w-40">
              {formatDay(d.date_from)}
              {d.date_to !== d.date_from && ` — ${formatDay(d.date_to)}`}
            </span>
            <span className="flex-1 truncate text-muted-foreground">
              {d.title}
              {!d.period_id && periodId && ` · ${T.allPeriods.toLowerCase()}`}
            </span>
            <Button variant="ghost" size="icon-sm" aria-label={T.remove} onClick={() => remove.mutate(d.id)}>
              <XIcon />
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-2 rounded-lg border p-3">
        <div className="grid grid-cols-2 gap-2">
          <Input type="date" aria-label={T.dayOffFrom} value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input type="date" aria-label={T.dayOffTo} value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Input placeholder={T.dayOffTitle} value={title} onChange={(e) => setTitle(e.target.value)} />
          <Button variant="outline" disabled={!from || create.isPending} onClick={add}>
            <PlusIcon /> {T.add}
          </Button>
        </div>
      </div>
    </div>
  )
}
