import { Navigate, useSearchParams } from 'react-router'

import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AreaList } from '@/features/areas/AreaList'
import { useAreaTypes } from '@/features/areas/useAreas'
import { SchedulePanel } from '@/features/schedule/SchedulePanel'
import { useCurrentPeriod } from '@/features/schedule/useCurrentPeriod'
import { AREA_SECTION_LABEL, AREAS_UI } from '@/lib/terms'

// До M22.2 задачи, заметки и проекты были вкладками этой страницы
const MOVED: Record<string, string> = { tasks: '/tasks', notes: '/notes', projects: '/projects' }

/** Сферы по типам и расписание; `?type=` — только один тип («Ученики» во вкладке). */
export function AreasPage() {
  const [params, setParams] = useSearchParams()
  const typeId = params.get('type') ?? undefined
  const { data: types } = useAreaTypes()
  const { period } = useCurrentPeriod()
  const oldTab = params.get('tab')
  if (oldTab && MOVED[oldTab]) return <Navigate to={MOVED[oldTab]} replace />
  const tab = oldTab === 'schedule' ? 'schedule' : 'areas'
  const areaType = typeId ? types?.find((t) => t.id === typeId) : undefined

  const setTab = (value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', value)
        return next
      },
      { replace: true },
    )

  if (typeId) {
    return (
      <>
        <PageHeader title={areaType?.name_plural ?? AREAS_UI.title} />
        <AreaList periodId={period?.id} typeId={typeId} />
      </>
    )
  }

  return (
    <>
      <PageHeader title={AREAS_UI.title} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="areas">{AREAS_UI.tab}</TabsTrigger>
          <TabsTrigger value="schedule">{AREA_SECTION_LABEL.schedule}</TabsTrigger>
        </TabsList>
        <TabsContent value="areas">
          <AreaList periodId={period?.id} />
        </TabsContent>
        <TabsContent value="schedule">
          <SchedulePanel />
        </TabsContent>
      </Tabs>
    </>
  )
}
