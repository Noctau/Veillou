import { CalendarCheckIcon, TimerIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { BacklogView } from '@/features/backlog/BacklogView'
import { FreeDialog } from '@/features/review/FreeDialog'

export function InboxPage() {
  const [free, setFree] = useState(false)
  return (
    <>
      <PageHeader
        title="Долгий ящик"
        actions={
          <Button variant="ghost" size="icon" asChild aria-label="Разбор недели">
            <Link to="/review/week">
              <CalendarCheckIcon />
            </Link>
          </Button>
        }
      />
      <Button variant="outline" className="mb-4 w-full" onClick={() => setFree(true)}>
        <TimerIcon /> У меня есть N минут
      </Button>
      <BacklogView />
      <FreeDialog open={free} onOpenChange={setFree} />
    </>
  )
}
