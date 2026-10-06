import { useSearchParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { useCurrentSemester } from '@/features/schedule/useCurrentSemester'
import { ProjectList } from '@/features/projects/ProjectList'
import { SubjectList } from '@/features/subjects/SubjectList'
import { TaskList } from '@/features/tasks/TaskList'

export function StudyPage() {
  const [params, setParams] = useSearchParams()
  const tab = (['schedule', 'tasks', 'projects'] as const).find((t) => t === params.get('tab')) ?? 'subjects'
  const { semester } = useCurrentSemester()

  const setTab = (value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', value)
        return next
      },
      { replace: true },
    )

  return (
    <>
      <PageHeader title="Учёба" />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="subjects">Предметы</TabsTrigger>
          <TabsTrigger value="tasks">Задания</TabsTrigger>
          <TabsTrigger value="projects">Проекты</TabsTrigger>
          <TabsTrigger value="schedule">Расписание</TabsTrigger>
        </TabsList>
        <TabsContent value="subjects">
          <SubjectList semesterId={semester?.id} />
        </TabsContent>
        <TabsContent value="tasks">
          <TaskList />
        </TabsContent>
        <TabsContent value="projects">
          <ProjectList />
        </TabsContent>
        <TabsContent value="schedule">
          <SchedulePanel />
        </TabsContent>
      </Tabs>
    </>
  )
}
