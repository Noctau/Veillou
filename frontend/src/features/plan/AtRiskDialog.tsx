import { CalendarClockIcon, ScissorsIcon, TimerIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { useSettings } from '@/features/settings/useSettings'
import { formatMinutes } from '@/features/tasks/labels'
import { useUpdateSubtask } from '@/features/tasks/useSubtasks'
import { type TaskDetail, useTask, useUpdateTask } from '@/features/tasks/useTasks'
import { addDaysIso, todayIn, wallDate } from '@/lib/time'

import { RISK_LABEL } from './labels'
import { type PlanRisk, usePreviewPlan, usePutDayLimit } from './usePlan'

type Props = {
  risk: PlanRisk | null
  onOpenChange: (open: boolean) => void
}

/**
 * Варианты, когда задание под угрозой (ТЗ §6, шаг 4): урезать оценки, больше учёбы
 * в конкретный день, сдвинуть внутренний срок. Решает пользователь; после выбора —
 * новое превью. «Убрать дела из ящика» появится, когда ящик попадёт в план (M11.2).
 */
export function AtRiskDialog({ risk, onOpenChange }: Props) {
  const { data: task } = useTask(risk?.task_id)
  return (
    <Dialog open={!!risk} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{risk?.task_title}</DialogTitle>
          <DialogDescription>Под угрозой: {risk && RISK_LABEL[risk.reason]}. Что можно сделать:</DialogDescription>
        </DialogHeader>
        {!task || !risk ? (
          <Skeleton className="h-48" />
        ) : (
          <Options key={task.id} task={task} risk={risk} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  )
}

const round5 = (min: number) => Math.max(5, Math.round(min / 5) * 5)

function Options({ task, risk, onDone }: { task: TaskDetail; risk: PlanRisk; onDone: () => void }) {
  const tz = useTimeZone()
  const { data: settings } = useSettings()
  const preview = usePreviewPlan()
  const updateTask = useUpdateTask()
  const updateSubtask = useUpdateSubtask(task.id)
  const putLimit = usePutDayLimit()

  const todo = task.subtasks.filter((s) => s.status === 'todo')
  const whole = todo.length === 0 && task.subtasks.length === 0
  const initial = whole
    ? { [task.id]: task.estimate_min ?? 60 }
    : Object.fromEntries(todo.map((s) => [s.id, s.estimate_min]))
  const [estimates, setEstimates] = useState<Record<string, number>>(initial)

  const today = todayIn(tz)
  const lastDay = risk.deadline ? wallDate(risk.deadline, tz) : addDaysIso(today, 13)
  const [day, setDay] = useState(today)
  const limitHours = (settings?.study_limit_min_per_day ?? 360) / 60
  const [hours, setHours] = useState(limitHours + 2)

  const buffer = task.deadline_buffer_days ?? settings?.deadline_buffer_days ?? 0
  const busy = preview.isPending || updateTask.isPending || updateSubtask.isPending || putLimit.isPending

  const replan = () => {
    preview.mutate({})
    onDone()
  }

  const saveEstimates = async () => {
    if (whole) {
      await updateTask.mutateAsync({ id: task.id, body: { estimate_min: estimates[task.id] } })
    } else {
      for (const s of todo) {
        if (estimates[s.id] !== s.estimate_min) {
          await updateSubtask.mutateAsync({ id: s.id, body: { estimate_min: estimates[s.id] } })
        }
      }
    }
    replan()
  }

  const rows = whole ? [{ id: task.id, title: task.title }] : todo

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ScissorsIcon className="size-4" /> Урезать оценки
        </h3>
        <ul className="flex flex-col gap-1.5">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm">{r.title}</span>
              <Input
                type="number"
                inputMode="numeric"
                min={5}
                step={5}
                aria-label={`Оценка «${r.title}», мин`}
                className="w-20"
                value={estimates[r.id] ?? ''}
                onChange={(e) => setEstimates({ ...estimates, [r.id]: Number(e.target.value) })}
              />
              <span className="w-8 text-xs text-muted-foreground">мин</span>
            </li>
          ))}
        </ul>
        <div className="flex justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              setEstimates(Object.fromEntries(Object.entries(estimates).map(([id, m]) => [id, round5(m * 0.75)])))
            }
          >
            −25% всем
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || Object.values(estimates).some((m) => !(m >= 5))}
            onClick={() => void saveEstimates()}
          >
            Сохранить и пересчитать
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Всего: {formatMinutes(Object.values(estimates).reduce((a, b) => a + (b || 0), 0))}
        </p>
      </section>

      <Separator />

      <section className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <TimerIcon className="size-4" /> Больше учёбы в один день
        </h3>
        <p className="text-xs text-muted-foreground">Обычно — до {limitHours} ч в день. Разово можно больше.</p>
        <div className="flex items-end gap-2">
          <div className="flex flex-1 flex-col gap-1">
            <Label htmlFor="risk-day">День</Label>
            <Input id="risk-day" type="date" min={today} max={lastDay} value={day} onChange={(e) => setDay(e.target.value)} />
          </div>
          <div className="flex w-24 flex-col gap-1">
            <Label htmlFor="risk-hours">Часов</Label>
            <Input
              id="risk-hours"
              type="number"
              inputMode="decimal"
              min={0.5}
              max={16}
              step={0.5}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !day || !(hours > 0 && hours <= 16)}
            onClick={() => putLimit.mutate({ day, minutes: Math.round(hours * 60) }, { onSuccess: replan })}
          >
            Пересчитать
          </Button>
        </div>
      </section>

      {buffer > 0 && task.deadline && (
        <>
          <Separator />
          <section className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <CalendarClockIcon className="size-4" /> Сдвинуть внутренний срок
            </h3>
            <p className="text-xs text-muted-foreground">
              Сейчас план старается закончить за {buffer} дн. до дедлайна. Можно — в сам день дедлайна.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="self-end"
              disabled={busy}
              onClick={() => updateTask.mutate({ id: task.id, body: { deadline_buffer_days: 0 } }, { onSuccess: replan })}
            >
              Заканчивать в день дедлайна
            </Button>
          </section>
        </>
      )}
    </div>
  )
}
