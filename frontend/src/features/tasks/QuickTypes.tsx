import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { CategoryIcon } from '@/features/catalog/CategoryIcon'
import { quickTypes, type TaskType, useTaskTypes } from '@/features/catalog/useCatalog'
import { useProjects } from '@/features/projects/useProjects'
import { QUICK_TYPE } from '@/lib/terms'
import { queryKeys } from '@/lib/queryKeys'
import { addDaysIso, todayIn, wallToUtc } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'

import { useCreateTask } from './useTasks'

const NONE = 'none'

type ButtonsProps = {
  /** Проект, из которого открыли: он важнее проекта типа. */
  projectId?: string
  variant?: 'outline' | 'ghost'
}

/** «Быстрые типы» — типы задач с правилом срока (бывшее «Задание с работы»): кнопкой в один шаг. */
export function QuickTypeButtons({ projectId, variant = 'outline' }: ButtonsProps) {
  const { data: types } = useTaskTypes()
  const [open, setOpen] = useState<TaskType | null>(null)
  const quick = quickTypes(types)
  if (!quick.length) return null
  return (
    <>
      {quick.map((t) => (
        <Button key={t.id} size="sm" variant={variant} onClick={() => setOpen(t)}>
          <CategoryIcon name={t.icon} /> {t.name}
        </Button>
      ))}
      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          {open && <QuickTypeForm taskType={open} projectId={projectId} onDone={() => setOpen(null)} />}
        </DialogContent>
      </Dialog>
    </>
  )
}

function QuickTypeForm({ taskType, projectId, onDone }: { taskType: TaskType; projectId?: string; onDone: () => void }) {
  const tz = useTimeZone()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: projects } = useProjects()
  const create = useCreateTask()
  const today = todayIn(tz)
  const days = taskType.deadline_rule?.kind === 'days' ? taskType.deadline_rule.days : 0
  const fallbackProject = projectId ?? taskType.default_project_id ?? NONE
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [issued, setIssued] = useState(today)
  const [deadline, setDeadline] = useState<string | null>(null)
  const [project, setProject] = useState<string | null>(null)
  const due = deadline ?? addDaysIso(issued || today, days)
  const chosenProject = project ?? fallbackProject

  const submit = () =>
    create.mutate(
      {
        title: title.trim(),
        task_type_id: taskType.id,
        description,
        issued_at: issued || null,
        deadline: due ? wallToUtc(due, '23:59', tz) : null,
        // Явный null — «без проекта»: проект типа не подставится
        project_id: chosenProject === NONE ? null : chosenProject,
        priority: 'normal',
        subtasks: [],
      },
      {
        onSuccess: (task) => {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects })
          onDone()
          toast.success(QUICK_TYPE.added(taskType.name))
          navigate(`/tasks/${task.id}`)
        },
      },
    )

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (title.trim()) submit()
      }}
    >
      <DialogHeader>
        <DialogTitle>{taskType.name}</DialogTitle>
        <DialogDescription>{QUICK_TYPE.description(days)}</DialogDescription>
      </DialogHeader>
      <Field>
        <FieldLabel htmlFor="qt-title">{QUICK_TYPE.title}</FieldLabel>
        <Input id="qt-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="qt-desc">{QUICK_TYPE.descriptionLabel}</FieldLabel>
        <Textarea id="qt-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        <FieldDescription>{QUICK_TYPE.filesHint}</FieldDescription>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="qt-issued">{QUICK_TYPE.issued}</FieldLabel>
          <Input id="qt-issued" type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="qt-deadline">{QUICK_TYPE.deadline}</FieldLabel>
          <Input id="qt-deadline" type="date" value={due} onChange={(e) => setDeadline(e.target.value)} />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor="qt-project">{QUICK_TYPE.project}</FieldLabel>
        <Select value={chosenProject} onValueChange={setProject}>
          <SelectTrigger id="qt-project" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{QUICK_TYPE.noProject}</SelectItem>
            {projects?.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={!title.trim() || create.isPending}>
          {QUICK_TYPE.submit}
        </Button>
      </DialogFooter>
    </form>
  )
}
