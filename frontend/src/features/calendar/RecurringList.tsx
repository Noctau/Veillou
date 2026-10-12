import { RepeatIcon } from 'lucide-react'
import { useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAreas } from '@/features/areas/useAreas'
import { describePattern, ruleLabel } from '@/features/schedule/pattern'
import { ScheduleRuleDialog } from '@/features/schedule/ScheduleRuleDialog'
import { type ScheduleRule, useEventTypes, useScheduleRules } from '@/features/schedule/useSchedule'
import { paletteColor } from '@/lib/colors'
import { EVENT_UI as T } from '@/lib/terms'
import { cn } from '@/lib/utils'

/** Повторы без периода (бывшие личные повторы) — правка и удаление правила. */
export function RecurringList() {
  const { data = [] } = useScheduleRules()
  const { data: types = [] } = useEventTypes()
  const { data: areas = [] } = useAreas()
  const [editing, setEditing] = useState<ScheduleRule | null>(null)
  const rules = data.filter((r) => !r.period_id)
  if (rules.length === 0) return null
  const typeOf = (r: ScheduleRule) => types.find((t) => t.id === r.event_type_id)
  const areaOf = (r: ScheduleRule) => areas.find((a) => a.id === r.area_id)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <RepeatIcon className="size-4" /> {T.recurring}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 pt-2">
        {rules.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setEditing(r)}
            className="flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-muted"
          >
            <span className={cn('size-2.5 shrink-0 rounded-full', paletteColor(r.color ?? areaOf(r)?.color ?? typeOf(r)?.color).bg)} />
            <span className="flex-1 truncate">{ruleLabel(r, areaOf(r), typeOf(r))}</span>
            <span className="text-muted-foreground">
              {describePattern(r.pattern)}
              {r.start_time && `, ${r.start_time}–${r.end_time}`}
            </span>
          </button>
        ))}
      </CardContent>
      <ScheduleRuleDialog
        open={!!editing}
        onOpenChange={(open) => !open && setEditing(null)}
        periodId={null}
        rule={editing ?? undefined}
      />
    </Card>
  )
}
