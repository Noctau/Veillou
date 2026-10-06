import { CalendarClockIcon } from 'lucide-react'
import { Link } from 'react-router'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useSubjects } from '@/features/subjects/useSubjects'
import { paletteColor } from '@/lib/colors'
import { cn } from '@/lib/utils'

import { describeDeadline } from './labels'
import { useTasks } from './useTasks'

const HORIZON_DAYS = 14
const LIMIT = 5

/** Активные задания с дедлайном в ближайшие 2 недели (и просроченные). */
export function DeadlinesCard({ tz, now }: { tz: string; now: Date }) {
  // Граница округлена до часа, чтобы ключ запроса не менялся каждую минуту
  const horizon = new Date(now)
  horizon.setMinutes(0, 0, 0)
  horizon.setDate(horizon.getDate() + HORIZON_DAYS)
  const { data: tasks, isPending } = useTasks({ status: ['active'], due_before: horizon.toISOString() })
  const { data: subjects } = useSubjects()
  const subjectById = new Map(subjects?.map((s) => [s.id, s]))
  const shown = tasks?.slice(0, LIMIT) ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClockIcon className="size-4" /> Ближайшие дедлайны
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-16" />}
        {tasks && tasks.length === 0 && (
          <p className="text-sm text-muted-foreground">Дедлайнов на ближайшие две недели нет.</p>
        )}
        <ul className="flex flex-col gap-1">
          {shown.map((t) => {
            const subject = t.subject_id ? subjectById.get(t.subject_id) : undefined
            const due = describeDeadline(t.deadline!, tz, now)
            return (
              <li key={t.id}>
                <Link to={`/tasks/${t.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted">
                  <span className={cn('h-8 w-1 shrink-0 rounded-full', subject ? paletteColor(subject.color).bg : 'bg-muted-foreground/40')} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">
                      {t.priority === 'high' && <span className="text-destructive">! </span>}
                      {t.title}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {subject && <span className="truncate">{subject.short_name || subject.name}</span>}
                      {t.subtasks_total > 0 && (
                        <>
                          <Progress value={t.progress * 100} className="h-1 w-12" aria-label="Прогресс" />
                          <span className="tabular-nums">
                            {t.subtasks_done}/{t.subtasks_total}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <span
                    className={cn(
                      'text-xs whitespace-nowrap',
                      due.tone === 'overdue' && 'font-medium text-destructive',
                      due.tone === 'soon' && 'font-medium text-foreground',
                      due.tone === 'normal' && 'text-muted-foreground',
                    )}
                  >
                    {due.text}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
        {tasks && tasks.length > LIMIT && (
          <Link to="/study?tab=tasks" className="mt-2 block px-2 text-xs text-muted-foreground underline-offset-4 hover:underline">
            Ещё {tasks.length - LIMIT}
          </Link>
        )}
      </CardContent>
    </Card>
  )
}
