import { PlusIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { WEEKDAYS_SHORT } from '@/lib/time'

import type { TimeWindow } from './useCatalog'

type Props = {
  value: TimeWindow[]
  onChange: (value: TimeWindow[]) => void
  /** Окно, которое добавляется кнопкой «Окно». */
  template?: TimeWindow
}

const DEFAULT_WINDOW: TimeWindow = { weekdays: [1, 2, 3, 4, 5], start: '10:00', end: '18:00' }

/** Список окон «дни недели × с–до». Конец раньше начала — до следующего утра. */
export function WindowsEditor({ value, onChange, template = DEFAULT_WINDOW }: Props) {
  const patch = (i: number, w: Partial<TimeWindow>) =>
    onChange(value.map((old, j) => (i === j ? { ...old, ...w } : old)))

  return (
    <div className="flex flex-col gap-3">
      {value.map((w, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-lg border p-3">
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            className="w-full"
            value={w.weekdays.map(String)}
            onValueChange={(days) => days.length && patch(i, { weekdays: days.map(Number).sort((a, b) => a - b) })}
          >
            {WEEKDAYS_SHORT.map((d, k) => (
              <ToggleGroupItem key={d} value={String(k + 1)} className="flex-1" aria-label={d}>
                {d}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <div className="flex items-center gap-2">
            <Input
              type="time"
              step={300}
              aria-label="С"
              value={w.start}
              onChange={(e) => e.target.value && patch(i, { start: e.target.value })}
            />
            <span className="text-muted-foreground">—</span>
            <Input
              type="time"
              step={300}
              aria-label="До"
              value={w.end}
              onChange={(e) => e.target.value && patch(i, { end: e.target.value })}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Убрать окно"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
            >
              <XIcon />
            </Button>
          </div>
          {w.end <= w.start && w.end !== w.start && (
            <p className="text-xs text-muted-foreground">До {w.end} следующего дня.</p>
          )}
          {w.end === w.start && <p className="text-xs text-destructive">Конец должен отличаться от начала.</p>}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, template])}>
        <PlusIcon /> Окно
      </Button>
    </div>
  )
}
