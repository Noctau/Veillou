import { useParams } from 'react-router'

import { BreakdownReview } from '@/features/breakdown/BreakdownReview'

export function BreakdownPage() {
  const { taskId } = useParams()
  return <BreakdownReview key={taskId} taskId={taskId!} />
}
