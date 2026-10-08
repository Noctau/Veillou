import { BookmarkPlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { formatMinutes, TASK_TYPE_LABEL } from '@/features/tasks/labels'
import type { TaskType } from '@/features/tasks/useTasks'

import { type Template, useCreateTemplate, useDeleteTemplate, useTemplates } from './useBreakdown'
import type { BreakdownStep } from './useBreakdown'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Текущие шаги — для «Сохранить как шаблон»; пусто — сохранять нечего. */
  steps: BreakdownStep[]
  taskType: TaskType
  defaultName: string
  onApply: (template: Template) => void
}

/** Шаблоны разбивки: применить без ИИ, сохранить текущую, удалить. */
export function TemplatesDialog({ open, onOpenChange, steps, taskType, defaultName, onApply }: Props) {
  const { data: templates } = useTemplates()
  const create = useCreateTemplate()
  const remove = useDeleteTemplate()
  const [name, setName] = useState(defaultName)
  // Подходящие по типу задания — сверху
  const sorted = [...(templates ?? [])].sort(
    (a, b) => Number(b.task_type === taskType) - Number(a.task_type === taskType),
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Шаблоны разбивки</DialogTitle>
          <DialogDescription>Готовый набор шагов — без ИИ, сразу.</DialogDescription>
        </DialogHeader>

        {sorted.length === 0 && <p className="text-sm text-muted-foreground">Пока нет шаблонов.</p>}
        <ul className="flex flex-col gap-1">
          {sorted.map((t) => (
            <li key={t.id} className="flex items-center gap-2">
              <button
                type="button"
                className="min-w-0 flex-1 rounded-md px-2 py-1.5 text-left hover:bg-muted"
                onClick={() => {
                  onApply(t)
                  onOpenChange(false)
                }}
              >
                <span className="block truncate text-sm font-medium">{t.name}</span>
                <span className="text-xs text-muted-foreground">
                  {t.task_type ? `${TASK_TYPE_LABEL[t.task_type]} · ` : ''}
                  {t.steps.length} шаг. · ~{formatMinutes(t.total_estimate_min)}
                </span>
              </button>
              <ConfirmButton title={`Удалить шаблон «${t.name}»?`} onConfirm={() => remove.mutate(t.id)}>
                <Button variant="ghost" size="icon" aria-label="Удалить шаблон" className="text-muted-foreground">
                  <Trash2Icon />
                </Button>
              </ConfirmButton>
            </li>
          ))}
        </ul>

        {steps.length > 0 && (
          <>
            <Separator />
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) create.mutate({ name: name.trim(), task_type: taskType, steps })
              }}
            >
              <Input value={name} onChange={(e) => setName(e.target.value)} aria-label="Название шаблона" />
              <Button type="submit" variant="outline" disabled={!name.trim() || create.isPending}>
                <BookmarkPlusIcon /> Сохранить
              </Button>
            </form>
            <p className="-mt-2 text-xs text-muted-foreground">Сохранить текущие шаги как шаблон.</p>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
