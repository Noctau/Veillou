import { InboxIcon, ListTodoIcon, Loader2Icon, SparklesIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { jobResult, type ParseDraft, useJob } from '@/features/ai/useJob'
import { TaskTypeSelect } from '@/features/catalog/CatalogSelect'
import { AreaSelect } from '@/features/areas/AreaSelect'
import { AREAS_UI } from '@/lib/terms'
import { wallDate, wallTime, wallToUtc } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'


export type AiCardResult = {
  kind: 'task' | 'backlog'
  title: string
  description: string
  task_type_id: string | null
  area_id: string | null
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
  const [kind, setKind] = useState<'task' | 'backlog'>(draft.kind === 'backlog' ? 'backlog' : 'task')
  const [title, setTitle] = useState(draft.title)
  const [taskTypeId, setTaskTypeId] = useState(draft.task_type_id ?? null)
  const [areaId, setAreaId] = useState(draft.area_id)
  const [day, setDay] = useState(draft.deadline ? wallDate(draft.deadline, tz) : '')
  const [description, setDescription] = useState(draft.description)
  const time = draft.deadline ? wallTime(draft.deadline, tz) : '23:59'

  const card = (): AiCardResult => ({
    kind,
    title: title.trim(),
    description,
    task_type_id: taskTypeId,
    area_id: areaId,
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
            <FieldLabel htmlFor="ai-area">{AREAS_UI.area}</FieldLabel>
            <AreaSelect id="ai-area" value={areaId} onChange={setAreaId} />
          </Field>
          <Field>
            <FieldLabel htmlFor="ai-type">Тип</FieldLabel>
            <TaskTypeSelect id="ai-type" value={taskTypeId} onChange={setTaskTypeId} />
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
