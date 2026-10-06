import { CalendarPlusIcon, CalendarXIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { ActionTypeSelect } from '@/features/catalog/CatalogSelect'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatDay, todayIn, wallDate, wallTime, wallToUtc } from '@/lib/time'

import { formatMinutes } from './labels'
import { useDeleteSubtask, useScheduleSubtask, useUnscheduleSubtask, useUpdateSubtask } from './useSubtasks'
import type { Subtask } from './useTasks'

type Props = {
  taskId: string
  subtask: Subtask | null
  siblings: Subtask[]
  onOpenChange: (open: boolean) => void
}

export function SubtaskDialog({ taskId, subtask, siblings, onOpenChange }: Props) {
  return (
    <Dialog open={!!subtask} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Шаг</DialogTitle>
        </DialogHeader>
        {subtask && (
          <SubtaskForm
            key={subtask.id}
            taskId={taskId}
            subtask={subtask}
            siblings={siblings.filter((s) => s.id !== subtask.id)}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SubtaskForm({
  taskId,
  subtask,
  siblings,
  onDone,
}: {
  taskId: string
  subtask: Subtask
  siblings: Subtask[]
  onDone: () => void
}) {
  const tz = useTimeZone()
  const update = useUpdateSubtask(taskId)
  const remove = useDeleteSubtask(taskId)
  const schedule = useScheduleSubtask(taskId)
  const unschedule = useUnscheduleSubtask(taskId)

  const [title, setTitle] = useState(subtask.title)
  const [estimate, setEstimate] = useState(String(subtask.estimate_min))
  const [actionTypeId, setActionTypeId] = useState(subtask.action_type_id)
  const [deps, setDeps] = useState<string[]>(subtask.depends_on)
  const [note, setNote] = useState(subtask.note)

  const block = subtask.events.find((e) => e.status === 'planned') ?? subtask.events[0]
  const [day, setDay] = useState(block ? wallDate(block.start, tz) : todayIn(tz))
  const [time, setTime] = useState(block ? wallTime(block.start, tz) : '18:00')

  const minutes = Number(estimate)
  const valid = title.trim() !== '' && Number.isInteger(minutes) && minutes >= 5 && minutes <= 600

  const save = () =>
    update.mutate(
      {
        id: subtask.id,
        body: { title: title.trim(), estimate_min: minutes, action_type_id: actionTypeId, depends_on: deps, note },
      },
      { onSuccess: onDone },
    )

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="st-title">Что сделать</FieldLabel>
        <Input id="st-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="st-estimate">Оценка, мин</FieldLabel>
          <Input
            id="st-estimate"
            type="number"
            inputMode="numeric"
            min={5}
            max={600}
            step={5}
            value={estimate}
            onChange={(e) => setEstimate(e.target.value)}
            aria-invalid={!valid}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="st-type">Тип действия</FieldLabel>
          <ActionTypeSelect id="st-type" value={actionTypeId} onChange={setActionTypeId} emptyLabel="Как у задания" />
        </Field>
      </div>

      {siblings.length > 0 && (
        <FieldSet>
          <FieldLegend variant="label">Сначала сделать</FieldLegend>
          <div className="flex flex-col gap-2">
            {siblings.map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={deps.includes(s.id)}
                  onCheckedChange={(checked) =>
                    setDeps((old) => (checked ? [...old, s.id] : old.filter((d) => d !== s.id)))
                  }
                />
                <span className="truncate">{s.title}</span>
              </label>
            ))}
          </div>
        </FieldSet>
      )}

      <Field>
        <FieldLabel htmlFor="st-note">Заметка</FieldLabel>
        <Textarea id="st-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>

      <Separator />

      <Field>
        <FieldLabel>В календарь</FieldLabel>
        {block && (
          <FieldDescription>
            Стоит: {formatDay(wallDate(block.start, tz))}, {wallTime(block.start, tz)}–{wallTime(block.end, tz)}
          </FieldDescription>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Input type="date" aria-label="День" className="w-auto" value={day} onChange={(e) => setDay(e.target.value)} />
          <Input type="time" step={300} aria-label="Начало" className="w-28" value={time} onChange={(e) => setTime(e.target.value)} />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!day || !time || schedule.isPending}
            onClick={() => schedule.mutate({ id: subtask.id, start: wallToUtc(day, time, tz) }, { onSuccess: onDone })}
          >
            <CalendarPlusIcon /> {block ? 'Перенести' : 'Поставить'}
          </Button>
          {block && (
            <Button type="button" variant="ghost" size="sm" onClick={() => unschedule.mutate(subtask.id)}>
              <CalendarXIcon /> Убрать
            </Button>
          )}
        </div>
        <FieldDescription>Займёт {formatMinutes(subtask.estimate_min)}. Блок закрепится — планировщик его не сдвинет.</FieldDescription>
      </Field>

      <DialogFooter className="flex-row items-center">
        <ConfirmButton title={`Удалить «${subtask.title}»?`} onConfirm={() => remove.mutate(subtask.id, { onSuccess: onDone })}>
          <Button type="button" variant="ghost" size="icon" aria-label="Удалить шаг" className="mr-auto text-destructive">
            <Trash2Icon />
          </Button>
        </ConfirmButton>
        <Button type="submit" disabled={!valid || update.isPending}>
          Сохранить
        </Button>
      </DialogFooter>
    </form>
  )
}
