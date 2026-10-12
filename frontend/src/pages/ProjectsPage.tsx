import { PageHeader } from '@/components/layout/PageHeader'
import { ProjectList } from '@/features/projects/ProjectList'
import { NAV_UI } from '@/lib/terms'

export function ProjectsPage() {
  return (
    <>
      <PageHeader title={NAV_UI.projects} />
      <ProjectList />
    </>
  )
}
