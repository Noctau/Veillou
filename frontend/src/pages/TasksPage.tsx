import { PageHeader } from '@/components/layout/PageHeader'
import { TaskList } from '@/features/tasks/TaskList'
import { NAV_UI } from '@/lib/terms'

export function TasksPage() {
  return (
    <>
      <PageHeader title={NAV_UI.tasks} />
      <TaskList />
    </>
  )
}
