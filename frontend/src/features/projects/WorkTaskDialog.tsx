import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { addDaysIso, todayIn, wallToUtc } from '@/lib/time'

import { useCreateWorkTask, useProjects } from './useProjects'

const WORK_DAYS = 14
const NONE = 'none'

type Props = { open: boolean; onOpenChange: (open: boolean) => void; projectId?: string }

/** «Задание с работы»: дедлайн = выдача + 14 дней, по умолчанию — в проект ВКР. */
export function WorkTaskDialog({ open, onOpenChange, projectId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Задание с работы</DialogTitle>
          <DialogDescription>Срок — две недели с выдачи. Можно поменять.</DialogDescription>
        </DialogHeader>
        {open && <WorkTaskForm projectId={projectId} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function WorkTaskForm({ projectId, onDone }: { projectId?: string; onDone: () => void }) {
  const tz = useTimeZone()
  const navigate = useNavigate()
  const { data: projects } = useProjects()
  const create = useCreateWorkTask()
  const today = todayIn(tz)
  const fallbackProject = projectId ?? projects?.find((p) => p.is_work_default)?.id ?? NONE
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [issued, setIssued] = useState(today)
  const [deadline, setDeadline] = useState<string | null>(null)
  const [project, setProject] = useState<string | null>(null)
  const due = deadline ?? addDaysIso(issued || today, WORK_DAYS)
  const chosenProject = project ?? fallbackProject

  const submit = () =>
    create.mutate(
      {
        title: title.trim(),
        description,
        issued_at: issued || null,
        deadline: due ? wallToUtc(due, '23:59', tz) : null,
        project_id: chosenProject === NONE ? null : chosenProject,
        no_project: chosenProject === NONE,
      },
      {
        onSuccess: (task) => {
          onDone()
          toast.success('Задание с работы добавлено')
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
      <Field>
        <FieldLabel htmlFor="wt-title">Что сделать</FieldLabel>
        <Input id="wt-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Обработать данные реанализа" />
      </Field>
      <Field>
        <FieldLabel htmlFor="wt-desc">Описание</FieldLabel>
        <Textarea id="wt-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        <FieldDescription>Файлы можно приложить на экране задания.</FieldDescription>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="wt-issued">Выдано</FieldLabel>
          <Input id="wt-issued" type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="wt-deadline">Срок</FieldLabel>
          <Input id="wt-deadline" type="date" value={due} onChange={(e) => setDeadline(e.target.value)} />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor="wt-project">Проект</FieldLabel>
        <Select value={chosenProject} onValueChange={setProject}>
          <SelectTrigger id="wt-project" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Без проекта</SelectItem>
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
          Добавить
        </Button>
      </DialogFooter>
    </form>
  )
}
