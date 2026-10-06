import { useParams } from 'react-router'

import { ProjectView } from '@/features/projects/ProjectView'

export function ProjectPage() {
  const { projectId } = useParams()
  return <ProjectView key={projectId} projectId={projectId!} />
}
