import { BriefcaseIcon, FlagIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/errors'
import { formatDay } from '@/lib/time'

import { ProjectDialog } from './ProjectDialog'
import { useProjects } from './useProjects'
import { WorkTaskDialog } from './WorkTaskDialog'

export function ProjectList() {
  const { data: projects, isPending, isError, error } = useProjects()
  const [creating, setCreating] = useState(false)
  const [workTask, setWorkTask] = useState(false)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
          <PlusIcon /> Проект
        </Button>
        <Button size="sm" variant="outline" onClick={() => setWorkTask(true)}>
          <BriefcaseIcon /> Задание с работы
        </Button>
      </div>
      {isPending && <Skeleton className="h-28" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {projects && projects.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Проектов нет. ВКР, поступление в магистратуру — всё, что на месяцы вперёд.
        </p>
      )}
      <ul className="grid gap-3 sm:grid-cols-2">
        {projects?.map((p) => {
          const total = p.tasks_total + p.milestones_total
          const done = p.tasks_done + p.milestones_done
          return (
            <li key={p.id}>
              <Link to={`/projects/${p.id}`} className="flex flex-col gap-2 rounded-xl border p-4 hover:bg-muted">
                <div className="flex items-baseline gap-2">
                  <span className="truncate font-medium">{p.title}</span>
                  {p.deadline && (
                    <span className="ml-auto text-xs whitespace-nowrap text-muted-foreground">
                      до {formatDay(p.deadline, { weekday: undefined, year: 'numeric' })}
                    </span>
                  )}
                </div>
                {total > 0 && <Progress value={(done / total) * 100} className="h-1.5" aria-label="Прогресс" />}
                <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                  <span>
                    задания {p.tasks_done}/{p.tasks_total}
                  </span>
                  <span>
                    этапы {p.milestones_done}/{p.milestones_total}
                  </span>
                  {p.is_work_default && (
                    <span className="flex items-center gap-1">
                      <BriefcaseIcon className="size-3" /> работа
                    </span>
                  )}
                </div>
                {p.next_milestone && (
                  <div className="flex items-center gap-1.5 text-sm">
                    <FlagIcon className="size-3.5 text-muted-foreground" />
                    <span className="truncate">{p.next_milestone.title}</span>
                    {p.next_milestone.date && (
                      <span className="ml-auto text-xs text-muted-foreground">{formatDay(p.next_milestone.date)}</span>
                    )}
                  </div>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
      <ProjectDialog open={creating} onOpenChange={setCreating} />
      <WorkTaskDialog open={workTask} onOpenChange={setWorkTask} />
    </div>
  )
}
