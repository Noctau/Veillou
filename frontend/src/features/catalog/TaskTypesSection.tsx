import { ChevronDownIcon, ChevronUpIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useTemplates } from '@/features/breakdown/useBreakdown'
import { useProjects } from '@/features/projects/useProjects'
import { TASK_TYPES_UI as T } from '@/lib/terms'

import { ActionTypeSelect, CategorySelect } from './CatalogSelect'
import { CategoryIcon } from './CategoryIcon'
import { IconPicker } from './IconPicker'
import {
  type CategoryIconName,
  type TaskType,
  useCreateTaskType,
  useDeleteTaskType,
  useTaskTypes,
  useUpdateTaskType,
} from './useCatalog'

const NONE = 'none'

type DeadlineKind = 'none' | 'days' | 'next_occurrence'

type Editing = { taskType?: TaskType } | null

export function TaskTypesSection() {
  const { data: types, isPending } = useTaskTypes()
  const [editing, setEditing] = useState<Editing>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{T.title}</CardTitle>
        <CardDescription>{T.description}</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={() => setEditing({})}>
            <PlusIcon /> {T.add}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-24" />}
        {types && types.length === 0 && <p className="text-sm text-muted-foreground">{T.empty}</p>}
        <ul className="flex flex-col">
          {types?.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => setEditing({ taskType: t })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
              >
                <CategoryIcon name={t.icon} className="size-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{t.name}</div>
                  {t.synonyms.length > 0 && (
                    <div className="truncate text-xs text-muted-foreground">{t.synonyms.join(', ')}</div>
                  )}
                </div>
                {t.deadline_rule && (
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t.deadline_rule.kind === 'days' ? T.deadlineChip(t.deadline_rule.days) : T.deadlineNextChip}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing?.taskType?.name ?? T.newTitle}</DialogTitle>
          </DialogHeader>
          {editing && <TaskTypeForm key={editing.taskType?.id ?? 'new'} taskType={editing.taskType} onDone={() => setEditing(null)} />}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/** «реферат, Эссе ,» → ["реферат", "Эссе"] */
function parseSynonyms(text: string): string[] {
  return text
    .split(',')
    .map((w) => w.trim())
    .filter(Boolean)
}

function TaskTypeForm({ taskType, onDone }: { taskType?: TaskType; onDone: () => void }) {
  const create = useCreateTaskType()
  const update = useUpdateTaskType()
  const remove = useDeleteTaskType()
  const { data: projects } = useProjects()
  const { data: templates } = useTemplates()
  const [name, setName] = useState(taskType?.name ?? '')
  const [icon, setIcon] = useState<CategoryIconName>(taskType?.icon ?? 'tag')
  const [synonyms, setSynonyms] = useState(taskType?.synonyms.join(', ') ?? '')
  const [actionTypeId, setActionTypeId] = useState(taskType?.default_action_type_id ?? null)
  const [categoryId, setCategoryId] = useState(taskType?.default_category_id ?? null)
  const [estimate, setEstimate] = useState(taskType?.default_estimate_min ? String(taskType.default_estimate_min) : '')
  const rule = taskType?.deadline_rule ?? null
  const [deadlineKind, setDeadlineKind] = useState<DeadlineKind>(rule?.kind ?? 'none')
  const [days, setDays] = useState(rule?.kind === 'days' ? String(rule.days) : '7')
  const [projectId, setProjectId] = useState(taskType?.default_project_id ?? NONE)
  const [templateId, setTemplateId] = useState(taskType?.default_template_id ?? NONE)
  // Базовые поля сразу, остальное — под «Подробнее» (у нового типа)
  const [more, setMore] = useState(!!taskType)
  const saving = create.isPending || update.isPending
  const estimateNum = estimate ? Number(estimate) : null
  const daysNum = Number(days)
  const valid =
    name.trim() !== '' &&
    (estimateNum === null || (Number.isInteger(estimateNum) && estimateNum >= 5 && estimateNum <= 10_000)) &&
    (deadlineKind !== 'days' || (Number.isInteger(daysNum) && daysNum >= 1 && daysNum <= 365))

  const save = () => {
    const body = {
      name: name.trim(),
      icon,
      synonyms: parseSynonyms(synonyms),
      default_action_type_id: actionTypeId,
      default_category_id: categoryId,
      default_estimate_min: estimateNum,
      deadline_rule:
        deadlineKind === 'days'
          ? { kind: 'days' as const, days: daysNum }
          : deadlineKind === 'next_occurrence'
            ? { kind: 'next_occurrence' as const }
            : null,
      default_project_id: projectId === NONE ? null : projectId,
      default_template_id: templateId === NONE ? null : templateId,
    }
    if (taskType) update.mutate({ id: taskType.id, body }, { onSuccess: onDone })
    else create.mutate(body, { onSuccess: onDone })
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="tt-name">{T.name}</FieldLabel>
        <Input id="tt-name" autoFocus={!taskType} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>{T.icon}</FieldLabel>
        <IconPicker value={icon} onChange={setIcon} />
      </Field>
      <Field>
        <FieldLabel htmlFor="tt-synonyms">{T.synonyms}</FieldLabel>
        <Input id="tt-synonyms" value={synonyms} onChange={(e) => setSynonyms(e.target.value)} />
        <FieldDescription>{T.synonymsHint}</FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor="tt-deadline">{T.deadline}</FieldLabel>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={deadlineKind} onValueChange={(v) => setDeadlineKind(v as DeadlineKind)}>
            <SelectTrigger id="tt-deadline" className="w-auto">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(['none', 'days', 'next_occurrence'] as const).map((k) => (
                <SelectItem key={k} value={k}>
                  {T.deadlineKinds[k]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {deadlineKind === 'days' && (
            <Input
              id="tt-days"
              aria-label={T.deadlineDays}
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="w-24"
            />
          )}
        </div>
        <FieldDescription>{T.deadlineHints[deadlineKind]}</FieldDescription>
      </Field>

      <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setMore((v) => !v)}>
        {more ? <ChevronUpIcon /> : <ChevronDownIcon />} {more ? T.less : T.more}
      </Button>
      {more && (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-2 gap-3">
            <Field>
              <FieldLabel htmlFor="tt-action">{T.actionType}</FieldLabel>
              <ActionTypeSelect id="tt-action" value={actionTypeId} onChange={setActionTypeId} emptyLabel={T.none} />
            </Field>
            <Field>
              <FieldLabel htmlFor="tt-category">{T.category}</FieldLabel>
              <CategorySelect id="tt-category" value={categoryId} onChange={setCategoryId} emptyLabel={T.none} />
            </Field>
          </div>
          <Field>
            <FieldLabel htmlFor="tt-estimate">{T.estimate}</FieldLabel>
            <Input
              id="tt-estimate"
              type="number"
              inputMode="numeric"
              min={5}
              step={5}
              value={estimate}
              onChange={(e) => setEstimate(e.target.value)}
              className="w-28"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="tt-project">{T.project}</FieldLabel>
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger id="tt-project" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{T.none}</SelectItem>
                {projects?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="tt-template">{T.template}</FieldLabel>
            <Select value={templateId} onValueChange={setTemplateId}>
              <SelectTrigger id="tt-template" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{T.none}</SelectItem>
                {templates?.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
      )}

      <DialogFooter className="flex-row items-center">
        {taskType && (
          <ConfirmButton
            title={T.deleteTitle(taskType.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(taskType.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" className="ml-auto" disabled={!valid || saving}>
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
