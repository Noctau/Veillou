import { PlusIcon, Undo2Icon, WandSparklesIcon } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { CalendarView } from '@/features/calendar/CalendarView'
import { PersonalEventDialog } from '@/features/calendar/PersonalEventDialog'
import { RecurringList } from '@/features/calendar/RecurringList'
import { usePlanState, usePreviewPlan, useUndoPlan } from '@/features/plan/usePlan'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { todayIn } from '@/lib/time'

export function CalendarPage() {
  const tz = useTimeZone()
  const [creating, setCreating] = useState(false)
  const { data: plan } = usePlanState()
  const preview = usePreviewPlan()
  const undo = useUndoPlan()
  return (
    <>
      <PageHeader
        title="Календарь"
        actions={
          <div className="flex gap-2">
            {plan?.undoable && !plan.proposal && (
              <Button size="sm" variant="ghost" disabled={undo.isPending} onClick={() => undo.mutate()}>
                <Undo2Icon /> <span className="max-sm:sr-only">Откатить план</span>
              </Button>
            )}
            <Button size="sm" variant="outline" disabled={preview.isPending} onClick={() => preview.mutate({})}>
              <WandSparklesIcon /> <span className="max-sm:sr-only">Перепланировать</span>
            </Button>
            <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
              <PlusIcon /> <span className="max-sm:sr-only">Событие</span>
            </Button>
          </div>
        }
      />
      <div className="flex flex-col gap-6">
        <CalendarView />
        <RecurringList />
      </div>
      <PersonalEventDialog open={creating} onOpenChange={setCreating} draft={{ date: todayIn(tz) }} />
    </>
  )
}
