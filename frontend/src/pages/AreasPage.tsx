import { useSearchParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AreaList } from '@/features/areas/AreaList'
import { NoteList } from '@/features/notes/NoteList'
import { ProjectList } from '@/features/projects/ProjectList'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { useCurrentSemester } from '@/features/schedule/useCurrentSemester'
import { TaskList } from '@/features/tasks/TaskList'
import { AREA_SECTION_LABEL, AREAS_UI } from '@/lib/terms'

const TABS = ['tasks', 'notes', 'projects', 'schedule'] as const

export function AreasPage() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.find((t) => t === params.get('tab')) ?? 'areas'
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
      <PageHeader title={AREAS_UI.title} />
      <Tabs value={tab} onValueChange={setTab}>
        {/* На 360 px вкладки не помещаются — прокрутка вбок */}
        <div className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none]">
          <TabsList className="mb-4">
            <TabsTrigger value="areas">{AREAS_UI.tab}</TabsTrigger>
            {TABS.map((t) => (
              <TabsTrigger key={t} value={t}>
                {AREA_SECTION_LABEL[t]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="areas">
          <AreaList periodId={semester?.id} />
        </TabsContent>
        <TabsContent value="tasks">
          <TaskList />
        </TabsContent>
        <TabsContent value="notes">
          <NoteList showArea />
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
