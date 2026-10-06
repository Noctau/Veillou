import { ArrowLeftIcon, CheckIcon, MoreVerticalIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { AttachmentList } from '@/features/attachments/AttachmentList'
import { ActionTypeSelect, CategorySelect } from '@/features/catalog/CatalogSelect'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { useSubjects } from '@/features/subjects/useSubjects'
import { errorMessage } from '@/lib/errors'
import { wallDate, wallTime, wallToUtc } from '@/lib/time'
import { cn } from '@/lib/utils'

import { describeDeadline, formatMinutes, TASK_TYPE_LABEL } from './labels'
import { SubtaskList } from './SubtaskList'
import { type TaskDetail, type TaskType, type TaskUpdate, useDeleteTask, useTask, useUpdateTask } from './useTasks'

const NONE = 'none'
const TASK_TYPES = Object.keys(TASK_TYPE_LABEL) as TaskType[]

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

/** Название, которое правится на месте и сохраняется по Enter / уходу фокуса. */
function TitleEditor({ task, onSave }: { task: TaskDetail; onSave: (title: string) => void }) {
  const [value, setValue] = useState(task.title)
  const commit = () => {
    const title = value.trim()
    if (title && title !== task.title) onSave(title)
    else setValue(task.title)
  }
  return (
    <Textarea
      value={value}
      rows={1}
      aria-label="Название задания"
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        }
      }}
      className={cn(
        'min-h-0 resize-none border-none bg-transparent! px-0 text-2xl font-semibold shadow-none focus-visible:ring-0 md:text-2xl',
        task.status === 'done' && 'text-muted-foreground line-through',
      )}
    />
  )
}

function DeadlineEditor({ task, onSave }: { task: TaskDetail; onSave: (deadline: string | null) => void }) {
  const tz = useTimeZone()
  const day = task.deadline ? wallDate(task.deadline, tz) : ''
  const time = task.deadline ? wallTime(task.deadline, tz) : '23:59'
  return (
    <div className="flex items-center gap-2">
      <Input
        type="date"
        aria-label="Дедлайн: день"
        value={day}
        onChange={(e) => onSave(e.target.value ? wallToUtc(e.target.value, time, tz) : null)}
      />
      <Input
        type="time"
        step={300}
        aria-label="Дедлайн: время"
        className="w-28"
        disabled={!day}
        value={day ? time : ''}
        onChange={(e) => day && e.target.value && onSave(wallToUtc(day, e.target.value, tz))}
      />
    </div>
  )
}

function Meta({ task, patch }: { task: TaskDetail; patch: (body: TaskUpdate) => void }) {
  const { data: subjects } = useSubjects()
  return (
    <Card>
      <CardContent className="grid grid-cols-1 gap-4 py-4 sm:grid-cols-2">
        <Field className="sm:col-span-2">
          <FieldLabel>Дедлайн</FieldLabel>
          <DeadlineEditor task={task} onSave={(deadline) => patch({ deadline })} />
        </Field>
        <Field>
          <FieldLabel htmlFor="task-subject">Предмет</FieldLabel>
          <Select value={task.subject_id ?? NONE} onValueChange={(v) => patch({ subject_id: v === NONE ? null : v })}>
            <SelectTrigger id="task-subject" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Без предмета</SelectItem>
              {subjects?.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="task-type">Тип</FieldLabel>
          <Select value={task.task_type} onValueChange={(v) => patch({ task_type: v as TaskType })}>
            <SelectTrigger id="task-type" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TASK_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {TASK_TYPE_LABEL[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="task-category">Категория</FieldLabel>
          <CategorySelect id="task-category" value={task.category_id} onChange={(category_id) => patch({ category_id })} />
        </Field>
        <Field>
          <FieldLabel htmlFor="task-action-type">Тип действия</FieldLabel>
          <ActionTypeSelect
            id="task-action-type"
            value={task.action_type_id}
            onChange={(action_type_id) => patch({ action_type_id })}
          />
        </Field>
        <Field className="sm:col-span-2">
          <FieldLabel>Важность</FieldLabel>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={task.priority}
            onValueChange={(v) => v && patch({ priority: v as TaskDetail['priority'] })}
          >
            <ToggleGroupItem value="normal">Обычная</ToggleGroupItem>
            <ToggleGroupItem value="high">Высокая</ToggleGroupItem>
          </ToggleGroup>
        </Field>
      </CardContent>
    </Card>
  )
}

function Description({ task, onSave }: { task: TaskDetail; onSave: (description: string) => void }) {
  const [value, setValue] = useState(task.description)
  return (
    <Textarea
      value={value}
      rows={4}
      placeholder="Текст задания, требования, ссылки…"
      aria-label="Описание"
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => value !== task.description && onSave(value)}
    />
  )
}

export function TaskView({ taskId }: { taskId: string }) {
  const navigate = useNavigate()
  const tz = useTimeZone()
  const { data: task, isPending, isError, error } = useTask(taskId)
  const update = useUpdateTask()
  const remove = useDeleteTask()
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  const patch = (body: TaskUpdate) => update.mutate({ id: task.id, body })
  const done = task.status === 'done'
  const due = task.deadline ? describeDeadline(task.deadline, tz) : null
  const estimate = task.subtasks.reduce((sum, s) => sum + (s.status === 'done' ? 0 : s.estimate_min), 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label="Назад" className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="min-w-0 flex-1">
          <TitleEditor key={task.title} task={task} onSave={(title) => patch({ title })} />
          <div className="flex flex-wrap gap-x-3 text-sm text-muted-foreground">
            <span>{TASK_TYPE_LABEL[task.task_type]}</span>
            {due && <span className={cn(due.tone === 'overdue' && !done && 'text-destructive')}>{due.text}</span>}
            {estimate > 0 && <span>осталось ~{formatMinutes(estimate)}</span>}
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Ещё">
              <MoreVerticalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2Icon /> Удалить задание
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-3">
        <Progress value={task.progress * 100} className="h-2 flex-1" aria-label="Прогресс" />
        <span className="text-sm text-muted-foreground tabular-nums">
          {task.subtasks_total ? `${task.subtasks_done} из ${task.subtasks_total}` : `${Math.round(task.progress * 100)}%`}
        </span>
        <Button size="sm" variant={done ? 'outline' : 'default'} onClick={() => patch({ status: done ? 'active' : 'done' })}>
          {done ? <RotateCcwIcon /> : <CheckIcon />}
          {done ? 'Вернуть' : 'Готово'}
        </Button>
      </div>

      <Section title="Шаги">
        <SubtaskList task={task} />
      </Section>

      <Section title="Описание">
        <Description key={task.description} task={task} onSave={(description) => patch({ description })} />
      </Section>

      <Section title="Файлы">
        <AttachmentList ownerType="task" ownerId={task.id} />
      </Section>

      <Meta task={task} patch={patch} />

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить «{task.title}»?</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => remove.mutate(task.id, { onSuccess: () => navigate('/study?tab=tasks', { replace: true }) })}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
