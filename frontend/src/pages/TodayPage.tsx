import { PageHeader } from '@/components/layout/PageHeader'
import { Placeholder } from '@/components/layout/Placeholder'
import { HealthBadge } from '@/features/health/HealthBadge'

export function TodayPage() {
  return (
    <>
      <PageHeader title="Сегодня" actions={<HealthBadge />} />
      <Placeholder text="Здесь будут пары, дела и дедлайны на сегодня." />
    </>
  )
}
