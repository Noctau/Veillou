import { useSearchParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { useCurrentSemester } from '@/features/schedule/useCurrentSemester'
import { SubjectList } from '@/features/subjects/SubjectList'

export function StudyPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'schedule' ? 'schedule' : 'subjects'
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
          <TabsTrigger value="schedule">Расписание</TabsTrigger>
        </TabsList>
        <TabsContent value="subjects">
          <SubjectList semesterId={semester?.id} />
        </TabsContent>
        <TabsContent value="schedule">
          <SchedulePanel />
        </TabsContent>
      </Tabs>
    </>
  )
}
