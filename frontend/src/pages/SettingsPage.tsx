import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ActionTypesSection } from '@/features/catalog/ActionTypesSection'
import { NotificationsSection } from '@/features/notifications/NotificationsSection'
import { CalibrationSection } from '@/features/plan/CalibrationSection'
import { CategoriesSection } from '@/features/catalog/CategoriesSection'
import { AccountSection } from '@/features/settings/sections/AccountSection'
import { DayModeSection } from '@/features/settings/sections/DayModeSection'
import { RemindersSection } from '@/features/settings/sections/RemindersSection'
import { RestSection } from '@/features/settings/sections/RestSection'
import { ScheduleSection } from '@/features/settings/sections/ScheduleSection'
import { StudySection } from '@/features/settings/sections/StudySection'
import { useSettings } from '@/features/settings/useSettings'
import { TelegramSection } from '@/features/telegram/TelegramSection'
import { errorMessage } from '@/lib/errors'

export function SettingsPage() {
  const { data: settings, isPending, isError, error, refetch } = useSettings()

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
        <div className="flex flex-col gap-4">
          <DayModeSection settings={settings} />
          <StudySection settings={settings} />
          <CalibrationSection />
          <RestSection settings={settings} />
          <ActionTypesSection />
          <CategoriesSection />
          <ScheduleSection settings={settings} />
          <RemindersSection settings={settings} />
          <NotificationsSection />
          <TelegramSection />
          <AccountSection />
        </div>
      )}
    </>
  )
}
