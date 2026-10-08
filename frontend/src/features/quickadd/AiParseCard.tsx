import { InboxIcon, ListTodoIcon, Loader2Icon, SparklesIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { jobResult, type ParseDraft, useJob } from '@/features/ai/useJob'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { useSubjects } from '@/features/subjects/useSubjects'
import { TASK_TYPE_LABEL } from '@/features/tasks/labels'
import type { TaskType } from '@/features/tasks/useTasks'
import { wallDate, wallTime, wallToUtc } from '@/lib/time'

const NONE = 'none'
const TASK_TYPES = Object.keys(TASK_TYPE_LABEL) as TaskType[]

export type AiCardResult = {
  kind: 'task' | 'backlog'
  title: string
  description: string
  task_type: TaskType
  subject_id: string | null
  deadline: string | null
  action_type_id: string | null
}

type Props = {
  jobId: string
  /** Создать; `breakDown` — сразу на экран разбивки. */
  onCreate: (card: AiCardResult, breakDown: boolean) => void
  /** Не ждать ИИ / ИИ не справился — создать по быстрому разбору. */
  onPlain: () => void
  onClose: () => void
  busy?: boolean
}

function Form({ draft, onCreate, busy }: { draft: ParseDraft; onCreate: Props['onCreate']; busy?: boolean }) {
  const tz = useTimeZone()
  const { data: subjects } = useSubjects()
  const [kind, setKind] = useState<'task' | 'backlog'>(draft.kind === 'backlog' ? 'backlog' : 'task')
  const [title, setTitle] = useState(draft.title)
  const [taskType, setTaskType] = useState<TaskType>(draft.task_type ?? 'other')
  const [subjectId, setSubjectId] = useState(draft.subject_id)
  const [day, setDay] = useState(draft.deadline ? wallDate(draft.deadline, tz) : '')
  const [description, setDescription] = useState(draft.description)
  const time = draft.deadline ? wallTime(draft.deadline, tz) : '23:59'

  const card = (): AiCardResult => ({
    kind,
    title: title.trim(),
    description,
    task_type: taskType,
    subject_id: subjectId,
    deadline: day ? wallToUtc(day, time, tz) : null,
    action_type_id: draft.action_type_id,
  })

  return (
    <div className="flex flex-col gap-3">
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        className="w-full"
        value={kind}
        onValueChange={(v) => v && setKind(v as 'task' | 'backlog')}
      >
        <ToggleGroupItem value="task" className="flex-1 gap-1">
          <ListTodoIcon className="size-4" /> Задание
        </ToggleGroupItem>
        <ToggleGroupItem value="backlog" className="flex-1 gap-1">
          <InboxIcon className="size-4" /> В ящик
        </ToggleGroupItem>
      </ToggleGroup>
      <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Название" />
      {kind === 'task' && (
        <div className="grid grid-cols-2 gap-2">
          <Field>
            <FieldLabel htmlFor="ai-subject">Предмет</FieldLabel>
            <Select value={subjectId ?? NONE} onValueChange={(v) => setSubjectId(v === NONE ? null : v)}>
              <SelectTrigger id="ai-subject" className="w-full">
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
            <FieldLabel htmlFor="ai-type">Тип</FieldLabel>
            <Select value={taskType} onValueChange={(v) => setTaskType(v as TaskType)}>
              <SelectTrigger id="ai-type" className="w-full">
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
        </div>
      )}
      <Field>
        <FieldLabel htmlFor="ai-deadline">{kind === 'task' ? 'Дедлайн' : 'Хорошо бы до'}</FieldLabel>
        <Input id="ai-deadline" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      </Field>
      {(description || kind === 'task') && (
        <Textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Требования задания"
          aria-label="Описание"
        />
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" disabled={busy || !title.trim()} onClick={() => onCreate(card(), false)}>
          Создать
        </Button>
        {kind === 'task' && (
          <Button disabled={busy || !title.trim()} onClick={() => onCreate(card(), true)}>
            <SparklesIcon /> Создать и разбить
          </Button>
        )}
      </div>
    </div>
  )
}

/** Карточка ИИ-разбора неуверенного ввода: поля правятся, «Создать и разбить» / «Создать». */
export function AiParseCard({ jobId, onCreate, onPlain, onClose, busy }: Props) {
  const { data: job } = useJob(jobId)
  const draft = jobResult(job, 'parse')

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-center gap-2">
          <SparklesIcon className="size-4 text-primary" />
          <span className="flex-1 truncate text-sm font-medium">
            {draft
              ? 'ИИ разобрал — проверьте'
              : job?.status === 'failed'
                ? 'ИИ не справился'
                : job?.waiting
                  ? 'ИИ сейчас недоступен — запрос в очереди'
                  : 'ИИ разбирает…'}
          </span>
          <Button variant="ghost" size="icon" className="size-7" aria-label="Закрыть" onClick={onClose}>
            <XIcon />
          </Button>
        </div>
        {draft && <Form draft={draft} onCreate={onCreate} busy={busy} />}
        {!draft && job?.status !== 'failed' && (
          <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
            <span className="flex items-center gap-2">
              <Loader2Icon className="size-4 animate-spin" />
              {job?.waiting ? 'Разберу, как только ИИ появится' : 'Обычно 5–30 секунд'}
            </span>
            <Button size="sm" variant="ghost" onClick={onPlain}>
              Не ждать — создать как есть
            </Button>
          </div>
        )}
        {job?.status === 'failed' && (
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="text-destructive">{job.error}</span>
            <Button size="sm" variant="outline" onClick={onPlain}>
              Создать как есть
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
