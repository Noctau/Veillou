import { type ReactNode, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AreaTypesSection } from '@/features/areas/AreaTypesSection'
import { ActionTypesSection } from '@/features/catalog/ActionTypesSection'
import { BudgetsSection } from '@/features/catalog/BudgetsSection'
import { CategoriesSection } from '@/features/catalog/CategoriesSection'
import { TaskTypesSection } from '@/features/catalog/TaskTypesSection'
import { DayProfilesSection } from '@/features/dayprofiles/DayProfilesSection'
import { NavSection } from '@/features/navigation/NavSection'
import { NotificationsSection } from '@/features/notifications/NotificationsSection'
import { CalibrationSection } from '@/features/plan/CalibrationSection'
import { EventTypesSection } from '@/features/schedule/EventTypesSection'
import { AboutSection } from '@/features/settings/sections/AboutSection'
import { AccountSection, PasswordSection } from '@/features/settings/sections/AccountSection'
import { RemindersSection } from '@/features/settings/sections/RemindersSection'
import { RestSection } from '@/features/settings/sections/RestSection'
import { ScheduleSection } from '@/features/settings/sections/ScheduleSection'
import { SpellcheckSection } from '@/features/settings/sections/SpellcheckSection'
import { StudySection } from '@/features/settings/sections/StudySection'
import { type SettingsTab, SETTINGS_TABS, tabFromParam } from '@/features/settings/tabs'
import { type UserSettings, useSettings } from '@/features/settings/useSettings'
import { BundleSection } from '@/features/setup/BundleSection'
import { TelegramSection } from '@/features/telegram/TelegramSection'
import { errorMessage } from '@/lib/errors'

/** Разделы каждой вкладки; вкладки и их подписи — features/settings/tabs.ts. */
function sections(tab: SettingsTab, settings: UserSettings): ReactNode {
  switch (tab) {
    case 'profile':
      return (
        <>
          <AboutSection settings={settings} />
          <AccountSection />
          <PasswordSection />
        </>
      )
    case 'planning':
      return (
        <>
          <StudySection settings={settings} />
          <DayProfilesSection />
          <RestSection settings={settings} />
          <BudgetsSection />
          <CalibrationSection />
        </>
      )
    case 'catalog':
      return (
        <>
          <AreaTypesSection />
          <EventTypesSection />
          <ActionTypesSection />
          <TaskTypesSection />
          <CategoriesSection />
          <BundleSection />
        </>
      )
    case 'notifications':
      return (
        <>
          <RemindersSection settings={settings} />
          <ScheduleSection settings={settings} />
          <NotificationsSection />
          <TelegramSection />
        </>
      )
    case 'interface':
      return (
        <>
          <NavSection settings={settings} />
          <SpellcheckSection />
        </>
      )
  }
}

export function SettingsPage() {
  const { data: settings, isPending, isError, error, refetch } = useSettings()
  const [params, setParams] = useSearchParams()
  const tab = tabFromParam(params.get('tab'))
  const strip = useRef<HTMLDivElement>(null)

  // Открыли по ссылке на дальнюю вкладку — на телефоне прокручиваем ленту к ней
  useEffect(() => {
    strip.current
      ?.querySelector<HTMLElement>('[data-state="active"]')
      ?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [tab, settings])

  const select = (value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', value)
        return next
      },
      { replace: true },
    )

  return (
    <>
      <PageHeader title="Настройки" />
      {isPending && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-48" />
        </div>
      )}
      {isError && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-destructive">{errorMessage(error)}</p>
          <Button variant="outline" onClick={() => refetch()}>
            Повторить
          </Button>
        </div>
      )}
      {settings && (
        <Tabs value={tab} onValueChange={select} className="gap-4">
          {/* На телефоне вкладки листаются вбок, страница — нет */}
          <div ref={strip} className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
            <TabsList className="h-9">
              {SETTINGS_TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="flex-none px-3">
                  <t.icon />
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {SETTINGS_TABS.map((t) => (
            <TabsContent key={t.id} value={t.id} className="flex flex-col gap-4">
              <p className="text-sm text-muted-foreground">{t.description}</p>
              {sections(t.id, settings)}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </>
  )
}
