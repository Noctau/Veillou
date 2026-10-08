import { PageHeader } from '@/components/layout/PageHeader'
import { WeeklyReview } from '@/features/review/WeeklyReview'

export function WeeklyReviewPage() {
  return (
    <>
      <PageHeader title="Разбор недели" />
      <WeeklyReview />
    </>
  )
}
