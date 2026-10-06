import { RepeatIcon } from 'lucide-react'
import { useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { paletteColor, KIND_COLORS } from '@/lib/colors'
import { cn } from '@/lib/utils'

import { PersonalEventDialog } from './PersonalEventDialog'
import { describeRrule } from './rrule'
import { type RecurringEvent, useRecurringEvents } from './useCalendar'

/** Личные блоки и отдых с повтором — правка и удаление серии. */
export function RecurringList() {
  const { data = [] } = useRecurringEvents()
  const [editing, setEditing] = useState<RecurringEvent | null>(null)
  if (data.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <RepeatIcon className="size-4" /> Повторяющиеся
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 pt-2">
        {data.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setEditing(r)}
            className="flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-muted"
          >
            <span className={cn('size-2.5 shrink-0 rounded-full', paletteColor(r.color ?? KIND_COLORS[r.kind]).bg)} />
            <span className="flex-1 truncate">{r.title}</span>
            <span className="text-muted-foreground">
              {describeRrule(r.rrule)}, {r.start_time}–{r.end_time}
            </span>
          </button>
        ))}
      </CardContent>
      <PersonalEventDialog
        open={!!editing}
        onOpenChange={(open) => !open && setEditing(null)}
        recurring={editing ?? undefined}
      />
    </Card>
  )
}
