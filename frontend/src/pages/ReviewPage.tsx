import { PageHeader } from '@/components/layout/PageHeader'
import { EveningReview } from '@/features/review/EveningReview'

export function ReviewPage() {
  return (
    <>
      <PageHeader title="Вечерний разбор" />
      <EveningReview />
    </>
  )
}
