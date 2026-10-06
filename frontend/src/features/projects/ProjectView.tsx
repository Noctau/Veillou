import { ArchiveIcon, ArrowLeftIcon, BriefcaseIcon, CheckIcon, MoreVerticalIcon, PlusIcon, RepeatIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { AttachmentList } from '@/features/attachments/AttachmentList'
import { describeRrule } from '@/features/calendar/rrule'
import { TaskList } from '@/features/tasks/TaskList'
import { useCreateTask, useTasks } from '@/features/tasks/useTasks'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { ContactsEditor } from './ContactsEditor'
import { MilestoneList } from './MilestoneList'
import { RecurringTaskDialog } from './RecurringTaskDialog'
import { type ProjectDetail, useDeleteProject, useProject, useUpdateProject } from './useProjects'
import { WorkTaskDialog } from './WorkTaskDialog'

function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className="pt-2">{children}</CardContent>
    </Card>
  )
}

function TextOnBlur({
  value,
  onSave,
  multiline,
  className,
  ...rest
}: {
  value: string
  onSave: (value: string) => void
  multiline?: boolean
  className?: string
  placeholder?: string
  'aria-label': string
}) {
  const [text, setText] = useState(value)
  const commit = () => text !== value && onSave(text)
  if (multiline) {
    return <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} className={className} {...rest} />
  }
  return (
    <Input
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => (text.trim() ? commit() : setText(value))}
      onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
      className={className}
      {...rest}
    />
  )
}

/** Быстро добавить разовое задание в проект. */
function AddProjectTask({ projectId }: { projectId: string }) {
  const create = useCreateTask()
  const [title, setTitle] = useState('')
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!title.trim()) return
        create.mutate({ title: title.trim(), task_type: 'other', description: '', priority: 'normal', project_id: projectId, subtasks: [] })
        setTitle('')
      }}
    >
      <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Новое задание в проект" aria-label="Новое задание" />
      <Button type="submit" size="icon" variant="outline" aria-label="Добавить задание" disabled={!title.trim()}>
        <PlusIcon />
      </Button>
    </form>
  )
}

function RecurringList({ projectId }: { projectId: string }) {
  const { data: tasks } = useTasks({ status: ['active'], project_id: projectId })
  const recurring = tasks?.filter((t) => t.recurrence) ?? []
  if (!recurring.length) {
    return <p className="text-sm text-muted-foreground">Например, встреча или письмо научруку раз в неделю.</p>
  }
  return (
    <ul className="flex flex-col gap-1">
      {recurring.map((t) => (
        <li key={t.id}>
          <Link to={`/tasks/${t.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted">
            <RepeatIcon className="size-4 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-sm">{t.title}</span>
            <span className="text-xs text-muted-foreground">{describeRrule(t.recurrence!)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Header({ project }: { project: ProjectDetail }) {
  const navigate = useNavigate()
  const update = useUpdateProject()
  const remove = useDeleteProject()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const patch = (body: Parameters<typeof update.mutate>[0]['body']) => update.mutate({ id: project.id, body })
  const done = project.status === 'done'
  const total = project.tasks_total + project.milestones_total
  const finished = project.tasks_done + project.milestones_done

  return (
    <>
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label="Назад" className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="min-w-0 flex-1">
          <TextOnBlur
            key={project.title}
            value={project.title}
            onSave={(title) => patch({ title: title.trim() })}
            aria-label="Название проекта"
            className={cn('h-auto border-none bg-transparent! px-0 text-2xl font-semibold shadow-none md:text-2xl', done && 'line-through')}
          />
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Итоговый срок</span>
            <Input
              type="date"
              aria-label="Итоговый срок"
              value={project.deadline ?? ''}
              onChange={(e) => patch({ deadline: e.target.value || null })}
              className="h-8 w-40"
            />
            {project.is_work_default && (
              <Badge variant="secondary">
                <BriefcaseIcon /> задания с работы
              </Badge>
            )}
            {project.status !== 'active' && <Badge variant="outline">{done ? 'Завершён' : 'В архиве'}</Badge>}
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Ещё">
              <MoreVerticalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuCheckboxItem
              checked={project.is_work_default}
              onCheckedChange={(checked) => patch({ is_work_default: checked })}
            >
              Сюда идут задания с работы
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            {project.status === 'active' ? (
              <>
                <DropdownMenuItem onSelect={() => patch({ status: 'done' })}>
                  <CheckIcon /> Завершить
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => patch({ status: 'archived' })}>
                  <ArchiveIcon /> В архив
                </DropdownMenuItem>
              </>
            ) : (
              <DropdownMenuItem onSelect={() => patch({ status: 'active' })}>
                <RotateCcwIcon /> Вернуть в работу
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2Icon /> Удалить проект
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {total > 0 && (
        <div className="flex items-center gap-3">
          <Progress value={(finished / total) * 100} className="h-2 flex-1" aria-label="Прогресс" />
          <span className="text-sm text-muted-foreground tabular-nums">
            {finished} из {total}
          </span>
        </div>
      )}
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить «{project.title}»?</AlertDialogTitle>
            <AlertDialogDescription>Этапы и файлы проекта удалятся, задания останутся без проекта.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => remove.mutate(project.id, { onSuccess: () => navigate('/study?tab=projects', { replace: true }) })}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

export function ProjectView({ projectId }: { projectId: string }) {
  const { data: project, isPending, isError, error } = useProject(projectId)
  const update = useUpdateProject()
  const [workTask, setWorkTask] = useState(false)
  const [recurring, setRecurring] = useState(false)

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  return (
    <div className="flex flex-col gap-4">
      <Header project={project} />

      <Section title="Этапы">
        <MilestoneList project={project} />
      </Section>

      <Section title="Задания">
        <div className="flex flex-col gap-3">
          <TaskList
            projectId={project.id}
            actions={
              <Button size="sm" variant="ghost" onClick={() => setWorkTask(true)}>
                <BriefcaseIcon /> С работы
              </Button>
            }
          />
          <AddProjectTask projectId={project.id} />
        </div>
      </Section>

      <Section
        title="Регулярно"
        action={
          <Button size="sm" variant="ghost" onClick={() => setRecurring(true)}>
            <PlusIcon /> Встреча
          </Button>
        }
      >
        <RecurringList projectId={project.id} />
      </Section>

      <Section title="Описание">
        <TextOnBlur
          key={project.description}
          multiline
          value={project.description}
          onSave={(description) => update.mutate({ id: project.id, body: { description } })}
          placeholder="Тема, цели, требования к работе…"
          aria-label="Описание проекта"
        />
      </Section>

      <Section title="Контакты">
        <ContactsEditor key={JSON.stringify(project.contacts)} project={project} />
      </Section>

      <Section title="Файлы">
        <AttachmentList ownerType="project" ownerId={project.id} />
      </Section>

      <WorkTaskDialog open={workTask} onOpenChange={setWorkTask} projectId={project.id} />
      <RecurringTaskDialog open={recurring} onOpenChange={setRecurring} projectId={project.id} />
    </div>
  )
}
