import { CalendarClockIcon, ClockIcon, InboxIcon, ScissorsIcon, SofaIcon, TimerIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useBacklog, useTakeForWeek } from '@/features/backlog/useBacklog'
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
 * Варианты, когда что-то под угрозой (ТЗ §6, шаг 4): урезать оценки, больше учёбы
 * в конкретный день, убрать дела из ящика с недели, сдвинуть внутренний срок.
 * Решает пользователь; после выбора — новое превью. Дело из ящика, которое не
 * влезло, можно снять с недели. Норма проекта не набирается — уменьшить её
 * или дать больше часов в конкретный день.
 */
export function AtRiskDialog({ risk, onOpenChange }: Props) {
  const isTask = risk?.group_kind === 'task'
  const { data: task } = useTask(isTask ? (risk?.task_id ?? undefined) : undefined)
  const close = () => onOpenChange(false)
  return (
    <Dialog open={!!risk} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{risk?.group_title}</DialogTitle>
          <DialogDescription>
            {risk?.group_kind === 'backlog'
              ? 'Дело из ящика не влезает в свободное время этой недели.'
              : risk?.group_kind === 'project'
                ? `Не набирается недельная норма проекта (${risk.title}).`
                : `Под угрозой: ${risk ? RISK_LABEL[risk.reason] : ''}. Что можно сделать:`}
          </DialogDescription>
        </DialogHeader>
        {risk?.group_kind === 'backlog' ? (
          <BacklogOptions risk={risk} onDone={close} />
        ) : risk?.group_kind === 'project' ? (
          <ProjectOptions risk={risk} onDone={close} />
        ) : risk?.group_kind === 'exam' ? (
          <div className="flex flex-col gap-4">
            {risk.reason === 'rest' && <RestNote />}
            <DayLimitSection deadline={risk.deadline} onDone={close} />
            <DropBacklogSection onDone={close} />
          </div>
        ) : !task || !risk ? (
          <Skeleton className="h-48" />
        ) : (
          <TaskOptions key={task.id} task={task} risk={risk} onDone={close} />
        )}
      </DialogContent>
    </Dialog>
  )
}

const round5 = (min: number) => Math.max(5, Math.round(min / 5) * 5)

function useReplan(onDone: () => void) {
  const preview = usePreviewPlan()
  return {
    pending: preview.isPending,
    replan: () => {
      preview.mutate({})
      onDone()
    },
  }
}

/** Причина — минимум отдыха: подсказка, где его поменять. */
function RestNote() {
  return (
    <section className="flex gap-2 rounded-lg bg-muted p-3 text-sm">
      <SofaIcon className="mt-0.5 size-4 shrink-0" />
      <p>
        Свободное время осталось только в защищённые вечера и полдня выходных. План их не трогает — минимум отдыха можно
        поменять в{' '}
        <Link to="/settings" className="text-primary underline-offset-4 hover:underline">
          Настройках
        </Link>
        .
      </p>
    </section>
  )
}

function TaskOptions({ task, risk, onDone }: { task: TaskDetail; risk: PlanRisk; onDone: () => void }) {
  const { data: settings } = useSettings()
  const updateTask = useUpdateTask()
  const updateSubtask = useUpdateSubtask(task.id)
  const { replan, pending } = useReplan(onDone)

  const todo = task.subtasks.filter((s) => s.status === 'todo')
  const whole = todo.length === 0 && task.subtasks.length === 0
  const initial = whole
    ? { [task.id]: task.estimate_min ?? 60 }
    : Object.fromEntries(todo.map((s) => [s.id, s.estimate_min]))
  const [estimates, setEstimates] = useState<Record<string, number>>(initial)

  const buffer = task.deadline_buffer_days ?? settings?.deadline_buffer_days ?? 0
  const busy = pending || updateTask.isPending || updateSubtask.isPending

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
      {risk.reason === 'rest' && <RestNote />}
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
      <DayLimitSection deadline={risk.deadline} onDone={onDone} />
      <DropBacklogSection onDone={onDone} />

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

/** «Больше учёбы в один день»: разовый лимит на дату. */
function DayLimitSection({ deadline, onDone }: { deadline: string | null; onDone: () => void }) {
  const tz = useTimeZone()
  const { data: settings } = useSettings()
  const putLimit = usePutDayLimit()
  const { replan, pending } = useReplan(onDone)
  const today = todayIn(tz)
  const lastDay = deadline ? wallDate(deadline, tz) : addDaysIso(today, 13)
  const [day, setDay] = useState(today)
  const limitHours = (settings?.study_limit_min_per_day ?? 360) / 60
  const [hours, setHours] = useState(limitHours + 2)

  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <TimerIcon className="size-4" /> Больше учёбы в один день
      </h3>
      <p className="text-xs text-muted-foreground">Обычно — до {limitHours} ч в день. Разово можно больше.</p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-36 flex-1 flex-col gap-1">
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
          disabled={pending || putLimit.isPending || !day || !(hours > 0 && hours <= 16)}
          onClick={() => putLimit.mutate({ day, minutes: Math.round(hours * 60) }, { onSuccess: replan })}
        >
          Пересчитать
        </Button>
      </div>
    </section>
  )
}

/** «Убрать дела из ящика»: снять взятые на неделю — их время отдать учёбе. */
function DropBacklogSection({ onDone }: { onDone: () => void }) {
  const { data: items } = useBacklog('active')
  const take = useTakeForWeek()
  const { replan, pending } = useReplan(onDone)
  const planned = (items ?? []).filter((i) => i.planned_week)
  if (!planned.length) return null
  return (
    <>
      <Separator />
      <section className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <InboxIcon className="size-4" /> Убрать дела из ящика
        </h3>
        <p className="text-xs text-muted-foreground">Они вернутся в следующий разбор недели.</p>
        <ul className="flex flex-col gap-1">
          {planned.map((i) => (
            <li key={i.id} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate">{i.title}</span>
              <Button
                size="sm"
                variant="ghost"
                disabled={pending || take.isPending}
                onClick={() => take.mutate({ id: i.id, take: false }, { onSuccess: replan })}
              >
                Снять
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

function BacklogOptions({ risk, onDone }: { risk: PlanRisk; onDone: () => void }) {
  const take = useTakeForWeek()
  const { replan, pending } = useReplan(onDone)
  return (
    <div className="flex flex-col gap-3 text-sm">
      {risk.reason === 'rest' && <RestNote />}
      <p className="text-muted-foreground">
        Сначала план ставит учёбу, дела из ящика — в оставшиеся окна, подходящие под их условия. Можно снять дело с недели:
        оно вернётся в следующий разбор.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Оставить
        </Button>
        <Button
          variant="outline"
          disabled={pending || take.isPending}
          onClick={() => take.mutate({ id: risk.group_id, take: false }, { onSuccess: replan })}
        >
          Снять с недели
        </Button>
      </div>
    </div>
  )
}

/** Норма проекта не набирается: сроки заданий важнее нормы, ящик — уступает ей. */
function ProjectOptions({ risk, onDone }: { risk: PlanRisk; onDone: () => void }) {
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="text-muted-foreground">
        Сначала план ставит задания со сроками, потом — время на проект, дела из ящика — после. На этой неделе свободного
        времени на всю норму не осталось.
      </p>
      <section className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 font-medium">
          <ClockIcon className="size-4" /> Поменять норму
        </h3>
        <p className="text-xs text-muted-foreground">Норма — в карточке проекта, раздел «Время на проект».</p>
        <Button asChild size="sm" variant="outline" className="self-end" onClick={onDone}>
          <Link to={`/projects/${risk.group_id}`}>Открыть проект</Link>
        </Button>
      </section>
      <Separator />
      <DayLimitSection deadline={risk.deadline} onDone={onDone} />
    </div>
  )
}
