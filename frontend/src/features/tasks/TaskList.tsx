import { PlusIcon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { byId, useTaskTypes } from '@/features/catalog/useCatalog'
import { useAreas } from '@/features/areas/useAreas'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { useTimeZone } from '@/lib/useTimeZone'
import { cn } from '@/lib/utils'

import { describeDeadline } from './labels'
import { type TaskStatus, useTasks } from './useTasks'

type Props = {
  areaId?: string
  projectId?: string
  /** Кнопки справа от фильтра (по умолчанию — «＋ Задание»). */
  actions?: ReactNode
}

/** Разовые задания: активные (ближайший дедлайн первым) или закрытые. Регулярные — отдельно. */
export function TaskList({ areaId, projectId, actions }: Props) {
  const tz = useTimeZone()
  const [status, setStatus] = useState<TaskStatus>('active')
  const query = useTasks({ status: [status], area_id: areaId, project_id: projectId })
  const { isPending, isError, error } = query
  const tasks = query.data?.filter((t) => !t.recurrence)
  const { data: areas } = useAreas()
  const areaById = new Map(areas?.map((s) => [s.id, s]))
  const taskTypes = byId(useTaskTypes().data)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <ToggleGroup type="single" variant="outline" size="sm" value={status} onValueChange={(v) => v && setStatus(v as TaskStatus)}>
          <ToggleGroupItem value="active">Активные</ToggleGroupItem>
          <ToggleGroupItem value="done">Сделанные</ToggleGroupItem>
        </ToggleGroup>
        <div className="ml-auto flex gap-1">
          {actions ?? (
            <Button asChild size="sm" variant="ghost">
              <Link to="/add">
                <PlusIcon /> Задание
              </Link>
            </Button>
          )}
        </div>
      </div>
      {isPending && <Skeleton className="h-32" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {tasks && tasks.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {status === 'active' ? 'Активных заданий нет.' : 'Пока ничего не сдано.'}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {tasks?.map((t) => {
          const area = t.area_id ? areaById.get(t.area_id) : undefined
          const due = t.deadline ? describeDeadline(t.deadline, tz) : null
          return (
            <li key={t.id}>
              <Link to={`/tasks/${t.id}`} className="flex items-center gap-3 rounded-lg border px-3 py-2.5 hover:bg-muted">
                <span className={cn('h-9 w-1 shrink-0 rounded-full', area ? paletteColor(area.color).bg : 'bg-muted-foreground/30')} />
                <div className="min-w-0 flex-1">
                  <div className={cn('truncate text-sm font-medium', status === 'done' && 'line-through')}>
                    {t.priority === 'high' && <span className="text-destructive">! </span>}
                    {t.title}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {t.task_type_id && taskTypes.has(t.task_type_id) && (
                      <span>{taskTypes.get(t.task_type_id)?.name}</span>
                    )}
                    {area && (
                      <span className="truncate">
                        {t.task_type_id && taskTypes.has(t.task_type_id) && '· '}
                        {area.short_name || area.name}
                      </span>
                    )}
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
                {due && (
                  <span
                    className={cn(
                      'text-xs whitespace-nowrap',
                      status === 'active' && due.tone === 'overdue' && 'font-medium text-destructive',
                      status === 'active' && due.tone === 'soon' && 'font-medium',
                      (status === 'done' || due.tone === 'normal') && 'text-muted-foreground',
                    )}
                  >
                    {due.text}
                  </span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
