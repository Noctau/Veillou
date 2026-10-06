import { PlusIcon } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { CalendarView } from '@/features/calendar/CalendarView'
import { PersonalEventDialog } from '@/features/calendar/PersonalEventDialog'
import { RecurringList } from '@/features/calendar/RecurringList'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { todayIn } from '@/lib/time'

export function CalendarPage() {
  const tz = useTimeZone()
  const [creating, setCreating] = useState(false)
  return (
    <>
      <PageHeader
        title="Календарь"
        actions={
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
            <PlusIcon /> Событие
          </Button>
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
