import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { todayIn } from '@/lib/time'
import { cn } from '@/lib/utils'

import { type Milestone, type ProjectDetail, useAddMilestone, useDeleteMilestone, useUpdateMilestone } from './useProjects'

function Row({ milestone, projectId, today }: { milestone: Milestone; projectId: string; today: string }) {
  const update = useUpdateMilestone(projectId)
  const remove = useDeleteMilestone()
  const [title, setTitle] = useState(milestone.title)
  const done = milestone.status === 'done'
  const late = !done && milestone.date && milestone.date < today
  return (
    <li className="flex flex-col">
      <div className="flex items-center gap-2">
        <Checkbox
          aria-label={done ? 'Не выполнен' : 'Выполнен'}
          className="size-5"
          checked={done}
          onCheckedChange={() => update.mutate({ id: milestone.id, body: { status: done ? 'planned' : 'done' } })}
        />
        <Input
          value={title}
          aria-label="Этап"
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title.trim() && title !== milestone.title && update.mutate({ id: milestone.id, body: { title: title.trim() } })}
          className={cn('border-transparent bg-transparent! shadow-none', done && 'text-muted-foreground line-through')}
        />
        <Input
          type="date"
          aria-label="Дата этапа"
          value={milestone.date ?? ''}
          onChange={(e) => update.mutate({ id: milestone.id, body: { date: e.target.value || null } })}
          className={cn('w-36 shrink-0', late && 'text-destructive')}
        />
        <ConfirmButton title={`Удалить этап «${milestone.title}»?`} description="Задания этапа останутся в проекте." onConfirm={() => remove.mutate(milestone.id)}>
          <Button variant="ghost" size="icon" aria-label="Удалить этап" className="shrink-0 text-muted-foreground">
            <Trash2Icon />
          </Button>
        </ConfirmButton>
      </div>
      {milestone.note && <p className="pl-7 text-xs text-muted-foreground">{milestone.note}</p>}
    </li>
  )
}

/** Этапы проекта: отметка, название и дата правятся на месте. Просроченные — красным. */
export function MilestoneList({ project }: { project: ProjectDetail }) {
  const tz = useTimeZone()
  const add = useAddMilestone(project.id)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const submit = () => {
    if (!title.trim()) return
    add.mutate({ title: title.trim(), date: date || null, note: '' })
    setTitle('')
    setDate('')
  }
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1">
        {project.milestones.map((m) => (
          <Row key={`${m.id}:${m.title}`} milestone={m} projectId={project.id} today={todayIn(tz)} />
        ))}
      </ul>
      <form
        className="flex items-center gap-2 pl-7"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Новый этап" aria-label="Новый этап" />
        <Input type="date" aria-label="Дата" value={date} onChange={(e) => setDate(e.target.value)} className="w-36 shrink-0" />
        <Button type="submit" size="icon" variant="outline" aria-label="Добавить этап" disabled={!title.trim()}>
          <PlusIcon />
        </Button>
      </form>
    </div>
  )
}
