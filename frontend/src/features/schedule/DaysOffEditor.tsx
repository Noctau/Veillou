import { PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDay } from '@/lib/time'

import { useCreateDayOff, useDaysOff, useDeleteDayOff } from './useSchedule'

/** Праздники и дни без пар. Пары в эти дни исчезают из календаря. */
export function DaysOffEditor() {
  const { data: daysOff = [] } = useDaysOff()
  const create = useCreateDayOff()
  const remove = useDeleteDayOff()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [title, setTitle] = useState('')

  const add = () =>
    create.mutate(
      { date_from: from, date_to: to || from, title },
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
      {daysOff.length === 0 && <p className="text-sm text-muted-foreground">Выходных пока нет.</p>}
      <ul className="flex flex-col gap-1">
        {daysOff.map((d) => (
          <li key={d.id} className="flex items-center gap-2 text-sm">
            <span className="w-40">
              {formatDay(d.date_from)}
              {d.date_to !== d.date_from && ` — ${formatDay(d.date_to)}`}
            </span>
            <span className="flex-1 truncate text-muted-foreground">{d.title}</span>
            <Button variant="ghost" size="icon-sm" aria-label="Удалить" onClick={() => remove.mutate(d.id)}>
              <XIcon />
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-2 rounded-lg border p-3">
        <div className="grid grid-cols-2 gap-2">
          <Input type="date" aria-label="С" value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input type="date" aria-label="По (необязательно)" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Input placeholder="Праздник, военка, практика…" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Button variant="outline" disabled={!from || create.isPending} onClick={add}>
            <PlusIcon /> Добавить
          </Button>
        </div>
      </div>
    </div>
  )
}
