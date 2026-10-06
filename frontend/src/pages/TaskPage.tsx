import { useParams } from 'react-router'

import { TaskView } from '@/features/tasks/TaskView'

export function TaskPage() {
  const { taskId } = useParams()
  return <TaskView key={taskId} taskId={taskId!} />
}
