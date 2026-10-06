import { PageHeader } from '@/components/layout/PageHeader'
import { BacklogView } from '@/features/backlog/BacklogView'

export function InboxPage() {
  return (
    <>
      <PageHeader title="Долгий ящик" />
      <BacklogView />
    </>
  )
}
