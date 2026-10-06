import { PageHeader } from '@/components/layout/PageHeader'
import { HealthBadge } from '@/features/health/HealthBadge'
import { TodayView } from '@/features/today/TodayView'

export function TodayPage() {
  return (
    <>
      <PageHeader title="Сегодня" actions={<HealthBadge />} />
      <TodayView />
    </>
  )
}
