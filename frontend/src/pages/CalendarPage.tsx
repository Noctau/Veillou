import { PlusIcon } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Placeholder } from '@/components/layout/Placeholder'
import { Button } from '@/components/ui/button'
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
      <div className="flex flex-col gap-4">
        <Placeholder text="Неделя и месяц появятся здесь." />
        <RecurringList />
      </div>
      <PersonalEventDialog open={creating} onOpenChange={setCreating} draft={{ date: todayIn(tz) }} />
    </>
  )
}
