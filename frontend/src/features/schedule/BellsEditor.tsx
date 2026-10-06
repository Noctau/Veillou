import { PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { WEEKDAYS_FULL, WEEKDAYS_SHORT } from '@/lib/time'

import { type BellSchedule, type BellScheduleIn, useReplaceBells } from './useSchedule'

type Slot = { number: number; start: string; end: string }
type Draft = { weekday: number | null; slots: Slot[] }

const DEFAULT_KEY = 'all'
const keyOf = (weekday: number | null) => (weekday === null ? DEFAULT_KEY : String(weekday))

function addMinutes(time: string, minutes: number): string {
  const [h, m] = time.split(':').map(Number)
  const total = Math.min(h * 60 + m + minutes, 23 * 60 + 59)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

/** Звонки семестра: общие + отдельные для конкретных дней недели. */
export function BellsEditor({ semesterId, bells }: { semesterId: string; bells: BellSchedule[] }) {
  const save = useReplaceBells(semesterId)
  const [drafts, setDrafts] = useState<Draft[]>(() =>
    bells.some((b) => b.weekday === null)
      ? bells.map((b) => ({ weekday: b.weekday, slots: b.slots.map((s) => ({ ...s })) }))
      : [{ weekday: null, slots: [] }, ...bells.map((b) => ({ weekday: b.weekday, slots: [...b.slots] }))],
  )
  const [active, setActive] = useState(DEFAULT_KEY)
  const [dirty, setDirty] = useState(false)

  const current = drafts.find((d) => keyOf(d.weekday) === active) ?? drafts[0]
  const overrideDays = drafts.filter((d) => d.weekday !== null).map((d) => d.weekday as number)
  const freeDays = [1, 2, 3, 4, 5, 6, 7].filter((d) => !overrideDays.includes(d))

  const change = (fn: (slots: Slot[]) => Slot[]) => {
    setDrafts((all) => all.map((d) => (d === current ? { ...d, slots: fn(d.slots) } : d)))
    setDirty(true)
  }

  const setSlot = (i: number, field: 'start' | 'end', value: string) =>
    change((slots) => slots.map((s, j) => (j === i ? { ...s, [field]: value } : s)))

  const addSlot = () =>
    change((slots) => {
      const last = slots.at(-1)
      const start = last ? addMinutes(last.end, 15) : '09:00'
      return [...slots, { number: (last?.number ?? 0) + 1, start, end: addMinutes(start, 95) }]
    })

  const removeSlot = (i: number) => change((slots) => slots.filter((_, j) => j !== i))

  const addOverride = (weekday: number) => {
    const base = drafts.find((d) => d.weekday === null)?.slots ?? []
    setDrafts((all) => [...all, { weekday, slots: base.map((s) => ({ ...s })) }])
    setActive(String(weekday))
    setDirty(true)
  }

  const removeOverride = () => {
    setDrafts((all) => all.filter((d) => d !== current))
    setActive(DEFAULT_KEY)
    setDirty(true)
  }

  const submit = () => {
    const schedules: BellScheduleIn[] = drafts
      .filter((d) => d.weekday === null || d.slots.length > 0)
      .map((d) => ({ weekday: d.weekday, slots: d.slots }))
    save.mutate(schedules, { onSuccess: () => setDirty(false) })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup type="single" variant="outline" size="sm" value={active} onValueChange={(v) => v && setActive(v)}>
          <ToggleGroupItem value={DEFAULT_KEY}>Все дни</ToggleGroupItem>
          {overrideDays.sort().map((d) => (
            <ToggleGroupItem key={d} value={String(d)}>
              {WEEKDAYS_SHORT[d - 1]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {freeDays.length > 0 && (
          <Select value="" onValueChange={(v) => addOverride(Number(v))}>
            <SelectTrigger size="sm" className="w-auto">
              <SelectValue placeholder="Свои для дня…" />
            </SelectTrigger>
            <SelectContent>
              {freeDays.map((d) => (
                <SelectItem key={d} value={String(d)}>
                  {WEEKDAYS_FULL[d - 1]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      <ul className="flex flex-col gap-2">
        {current.slots.map((slot, i) => (
          <li key={i} className="grid grid-cols-[1.25rem_minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-2">
            <span className="text-sm text-muted-foreground">{slot.number}</span>
            <Input
              type="time"
              step={300}
              aria-label={`${slot.number} пара: начало`}
              value={slot.start}
              onChange={(e) => setSlot(i, 'start', e.target.value)}
            />
            <Input
              type="time"
              step={300}
              aria-label={`${slot.number} пара: конец`}
              value={slot.end}
              onChange={(e) => setSlot(i, 'end', e.target.value)}
            />
            {i === current.slots.length - 1 ? (
              <Button variant="ghost" size="icon" aria-label="Убрать пару" onClick={() => removeSlot(i)}>
                <XIcon />
              </Button>
            ) : (
              <span />
            )}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={addSlot}>
          <PlusIcon /> Пара
        </Button>
        {current.weekday !== null && (
          <Button variant="ghost" size="sm" onClick={removeOverride}>
            Как во все дни
          </Button>
        )}
        <Button className="ml-auto" disabled={!dirty || save.isPending} onClick={submit}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить звонки'}
        </Button>
      </div>
    </div>
  )
}
