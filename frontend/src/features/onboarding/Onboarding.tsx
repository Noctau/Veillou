import { ChevronLeftIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { NotificationsSection } from '@/features/notifications/NotificationsSection'
import { PeriodForm } from '@/features/schedule/PeriodForm'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { SlotGridEditor } from '@/features/schedule/SlotGridEditor'
import { useCurrentPeriod } from '@/features/schedule/useCurrentPeriod'
import { groupGrids, useSlotGrids } from '@/features/schedule/useSchedule'
import { DayProfilesSection } from '@/features/dayprofiles/DayProfilesSection'
import { RestSection } from '@/features/settings/sections/RestSection'
import { useSettings } from '@/features/settings/useSettings'
import { TelegramSection } from '@/features/telegram/TelegramSection'

import { useFinishOnboarding } from './useOnboarding'

type Step = { title: string; hint: string; body: (next: () => void) => ReactNode }

function PeriodStep({ next }: { next: () => void }) {
  const { period, select, today, isPending } = useCurrentPeriod()
  if (isPending) return <Skeleton className="h-64" />
  return (
    <Card>
      <CardContent className="pt-4">
        <PeriodForm
          key={period?.id ?? 'new'}
          period={period}
          today={today}
          withDefaultSlots
          onDone={(s) => {
            select(s.id)
            next()
          }}
        />
      </CardContent>
    </Card>
  )
}

function SlotsStep() {
  const { period } = useCurrentPeriod()
  const { data: rows, isPending } = useSlotGrids()
  if (!period) return <p className="text-sm text-muted-foreground">Без периода сетка не нужна — этот шаг можно пропустить.</p>
  const grid = groupGrids(rows ?? []).find((g) => g.period_id === period.id)
  return (
    <Card>
      <CardContent className="pt-4">
        {isPending ? <Skeleton className="h-40" /> : <SlotGridEditor key={grid?.id ?? 'new'} grid={grid} periodId={period.id} />}
      </CardContent>
    </Card>
  )
}

function DayModeStep() {
  const { data: settings } = useSettings()
  if (!settings) return <Skeleton className="h-64" />
  return (
    <div className="flex flex-col gap-4">
      <DayProfilesSection />
      <RestSection settings={settings} />
    </div>
  )
}

const STEPS: Step[] = [
  {
    title: 'Период',
    hint: 'Если у занятости есть границы и цикл недель (семестр, четверть) — заведите период. Нет — пропустите шаг.',
    body: (next) => <PeriodStep next={next} />,
  },
  {
    title: 'Сетка слотов',
    hint: 'Номера и время (звонки, уроки). Стандартные уже подставлены — поправьте и сохраните.',
    body: () => <SlotsStep />,
  },
  {
    title: 'Расписание',
    hint: 'Добавьте правила: что и когда повторяется. Тип занятости и сферу можно завести прямо в диалоге.',
    body: () => <SchedulePanel />,
  },
  {
    title: 'Часы, сон и отдых',
    hint: 'Когда можно ставить дела и сколько свободных вечеров оставить. Не забудьте «Сохранить».',
    body: () => <DayModeStep />,
  },
  {
    title: 'Уведомления',
    hint: 'Напоминания перед событиями, о дедлайнах и утренняя сводка. Включите push на этом телефоне.',
    body: () => <NotificationsSection />,
  },
  {
    title: 'Telegram',
    hint: 'Бот дублирует напоминания и принимает дела сообщением. Можно подключить позже в Настройках.',
    body: () => <TelegramSection />,
  },
]

/** Короткая первичная настройка: период → сетка → расписание → часы/сон → push → Telegram. */
export function Onboarding() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const finish = useFinishOnboarding()
  const index = Math.min(Math.max(Number(params.get('step')) || 0, 0), STEPS.length - 1)
  const step = STEPS[index]
  const last = index === STEPS.length - 1

  const go = (i: number) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('step', String(i))
        return next
      },
      { replace: true },
    )
  const done = () => finish.mutate(undefined, { onSuccess: () => navigate('/', { replace: true }) })
  const next = () => (last ? done() : go(index + 1))

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-4 px-4 pt-4 pb-28">
      <header className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          {index > 0 ? (
            <Button variant="ghost" size="icon" aria-label="Назад" onClick={() => go(index - 1)}>
              <ChevronLeftIcon />
            </Button>
          ) : (
            <span className="text-lg font-semibold">Veillou</span>
          )}
          <span className="text-sm text-muted-foreground">
            Шаг {index + 1} из {STEPS.length}
          </span>
          <Button variant="ghost" size="sm" className="ml-auto" disabled={finish.isPending} onClick={done}>
            Пропустить всё
          </Button>
        </div>
        <Progress value={((index + 1) / STEPS.length) * 100} className="h-1.5" aria-label="Прогресс настройки" />
      </header>

      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{step.title}</h1>
        <p className="text-sm text-muted-foreground">{step.hint}</p>
      </div>

      {step.body(next)}

      <footer className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="mx-auto flex max-w-3xl gap-2 px-4 py-3">
          <Button className="flex-1" disabled={finish.isPending} onClick={next}>
            {last ? 'Готово' : 'Дальше'}
          </Button>
        </div>
      </footer>
    </div>
  )
}
