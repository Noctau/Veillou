import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { weekdaysToRrule } from '@/features/calendar/rrule'
import { useActionTypes } from '@/features/catalog/useCatalog'
import { useCreateTask } from '@/features/tasks/useTasks'
import { WEEKDAYS_SHORT } from '@/lib/time'

type Props = { open: boolean; onOpenChange: (open: boolean) => void; projectId: string }

/** Регулярная задача проекта («встреча с научруком по чт») — тип «связь с людьми». */
export function RecurringTaskDialog({ open, onOpenChange, projectId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Регулярная встреча</DialogTitle>
          <DialogDescription>Каждое повторение станет шагом; планировщик поставит его в рабочее время.</DialogDescription>
        </DialogHeader>
        {open && <RecurringForm projectId={projectId} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function RecurringForm({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const { data: actionTypes } = useActionTypes()
  const create = useCreateTask()
  const [title, setTitle] = useState('Встреча с научруком')
  const [days, setDays] = useState<string[]>(['4'])
  const [estimate, setEstimate] = useState('60')
  const minutes = Number(estimate)
  const valid = title.trim() !== '' && days.length > 0 && minutes >= 5 && minutes <= 600

  const submit = () =>
    create.mutate(
      {
        title: title.trim(),
        task_type: 'other',
        description: '',
        priority: 'normal',
        project_id: projectId,
        action_type_id: actionTypes?.find((a) => a.key === 'people')?.id ?? null,
        recurrence: weekdaysToRrule(days.map(Number)),
        estimate_min: minutes,
        subtasks: [],
      },
      { onSuccess: onDone },
    )

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) submit()
      }}
    >
      <Field>
        <FieldLabel htmlFor="rt-title">Что</FieldLabel>
        <Input id="rt-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>По каким дням</FieldLabel>
        <ToggleGroup type="multiple" variant="outline" size="sm" className="w-full" value={days} onValueChange={setDays}>
          {WEEKDAYS_SHORT.map((d, i) => (
            <ToggleGroupItem key={d} value={String(i + 1)} className="flex-1">
              {d}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <Field>
        <FieldLabel htmlFor="rt-estimate">Длительность, мин</FieldLabel>
        <Input id="rt-estimate" type="number" inputMode="numeric" min={5} max={600} step={5} className="w-28" value={estimate} onChange={(e) => setEstimate(e.target.value)} />
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={!valid || create.isPending}>
          Добавить
        </Button>
      </DialogFooter>
    </form>
  )
}
