import { ChevronLeftIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { BudgetsSection } from '@/features/catalog/BudgetsSection'
import { DayProfilesSection } from '@/features/dayprofiles/DayProfilesSection'
import { NotificationsSection } from '@/features/notifications/NotificationsSection'
import { EventTypesSection } from '@/features/schedule/EventTypesSection'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { RestSection } from '@/features/settings/sections/RestSection'
import { useSettings, useUpdateSettings } from '@/features/settings/useSettings'
import { SetupFlow } from '@/features/setup/SetupFlow'
import { TelegramSection } from '@/features/telegram/TelegramSection'
import { ONBOARDING_UI as T } from '@/lib/terms'

import { TimezonePicker } from './TimezonePicker'
import { useFinishOnboarding } from './useOnboarding'

type Step = { title: string; hint: string; body: (next: () => void) => ReactNode }

function WithSettings({ children }: { children: (settings: NonNullable<ReturnType<typeof useSettings>['data']>) => ReactNode }) {
  const { data: settings } = useSettings()
  return settings ? children(settings) : <Skeleton className="h-64" />
}

/** «Чем вы заняты?»: описание → ИИ-настройка; «Настрою сам» — текст уходит в «О себе». */
function AboutStep({ next }: { next: () => void }) {
  const update = useUpdateSettings()
  return (
    <SetupFlow
      intro={false}
      onApplied={next}
      manual={(text) => {
        if (text) update.mutate({ about: text })
        next()
      }}
    />
  )
}

const STEPS: Step[] = [
  {
    title: T.steps.timezone.title,
    hint: T.steps.timezone.hint,
    body: () => (
      <Card>
        <CardContent className="pt-4">
          <TimezonePicker />
        </CardContent>
      </Card>
    ),
  },
  { title: T.steps.about.title, hint: T.steps.about.hint, body: (next) => <AboutStep next={next} /> },
  {
    title: T.steps.schedule.title,
    hint: T.steps.schedule.hint,
    body: () => (
      <div className="flex flex-col gap-4">
        <EventTypesSection />
        <SchedulePanel />
      </div>
    ),
  },
  { title: T.steps.days.title, hint: T.steps.days.hint, body: () => <DayProfilesSection /> },
  {
    title: T.steps.limits.title,
    hint: T.steps.limits.hint,
    body: () => (
      <div className="flex flex-col gap-4">
        <BudgetsSection />
        <WithSettings>{(settings) => <RestSection settings={settings} />}</WithSettings>
      </div>
    ),
  },
  { title: T.steps.notifications.title, hint: T.steps.notifications.hint, body: () => <NotificationsSection /> },
  { title: T.steps.telegram.title, hint: T.steps.telegram.hint, body: () => <TelegramSection /> },
]

/**
 * Онбординг v2 (M22.1): пояс → «Чем вы заняты?» (ИИ-настройка или «настрою сам») →
 * занятость → режимы дня → лимиты и отдых → уведомления → Telegram. Любой шаг
 * пропускается; «Пропустить всё» — нулевая настройка: «Будни» / «Выходные» и типы
 * действий по умолчанию, без сфер и занятости.
 */
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
        next.delete('setupJob')
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
            <Button variant="ghost" size="icon" aria-label={T.back} onClick={() => go(index - 1)}>
              <ChevronLeftIcon />
            </Button>
          ) : (
            <span className="text-lg font-semibold">Veillou</span>
          )}
          <span className="text-sm text-muted-foreground">{T.progress(index + 1, STEPS.length)}</span>
          <Button variant="ghost" size="sm" className="ml-auto" disabled={finish.isPending} onClick={done}>
            {T.skipAll}
          </Button>
        </div>
        <Progress value={((index + 1) / STEPS.length) * 100} className="h-1.5" aria-label={T.progressLabel} />
      </header>

      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{step.title}</h1>
        <p className="text-sm text-muted-foreground">{step.hint}</p>
      </div>

      {step.body(next)}

      <footer className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="mx-auto flex max-w-3xl gap-2 px-4 py-3">
          <Button className="flex-1" disabled={finish.isPending} onClick={next}>
            {last ? T.finish : T.next}
          </Button>
        </div>
      </footer>
    </div>
  )
}
