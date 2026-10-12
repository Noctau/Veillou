import { ArrowLeftIcon, PencilIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PrepPanel } from '@/features/prep/PrepPanel'
import { NoteList } from '@/features/notes/NoteList'
import { ProjectList } from '@/features/projects/ProjectList'
import { usePeriods } from '@/features/schedule/useSchedule'
import { SourceList } from '@/features/sources/SourceList'
import { TaskList } from '@/features/tasks/TaskList'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { AREA_SECTION_LABEL, AREAS_UI as T } from '@/lib/terms'
import { cn } from '@/lib/utils'

import { AreaDialog } from './AreaDialog'
import { AreaSchedule } from './AreaSchedule'
import { FieldValuesView } from './FieldValuesView'
import { type Area, type AreaSection, type AreaType, useAreas, useAreaTypes } from './useAreas'

function Header({ area, areaType, areas, onEdit }: { area: Area; areaType?: AreaType; areas: Area[]; onEdit: () => void }) {
  const navigate = useNavigate()
  const { data: periods } = usePeriods()
  const period = periods?.find((p) => p.id === area.period_id)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label={T.back} className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="flex min-w-0 flex-1 items-start gap-2 pt-0.5">
          <span className={cn('mt-2 size-3 shrink-0 rounded-full', paletteColor(area.color).bg)} aria-hidden />
          <div className="min-w-0">
            <h1 className="text-2xl leading-tight font-semibold">{area.name}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {areaType && <span>{areaType.name}</span>}
              {area.short_name && <span>· {area.short_name}</span>}
              {period && <span>· {period.name}</span>}
              {area.archived_at && <Badge variant="secondary">{T.archived}</Badge>}
            </div>
          </div>
        </div>
        <Button variant="ghost" size="icon" aria-label={T.edit} onClick={onEdit}>
          <PencilIcon />
        </Button>
      </div>
      {areaType && <FieldValuesView defs={areaType.fields} values={area.fields} areas={areas} className="pl-9" />}
      {area.notes && <p className="pl-9 text-sm whitespace-pre-line text-muted-foreground">{area.notes}</p>}
    </div>
  )
}

function SectionContent({ section, area }: { section: AreaSection; area: Area }) {
  switch (section) {
    case 'schedule':
      return <AreaSchedule area={area} />
    case 'tasks':
      return <TaskList areaId={area.id} />
    case 'notes':
      return <NoteList areaId={area.id} />
    case 'materials':
      return <SourceList areaId={area.id} />
    case 'prep':
      return <PrepPanel areaId={area.id} />
    case 'projects':
      return <ProjectList areaId={area.id} />
  }
}

/** Страница сферы: всё по сфере в одном месте; разделы — из типа сферы. */
export function AreaView({ areaId }: { areaId: string }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { data: areas, isPending, isError, error } = useAreas()
  const { data: types } = useAreaTypes()
  const [editing, setEditing] = useState(false)
  const area = areas?.find((a) => a.id === areaId)
  const areaType = types?.find((t) => t.id === area?.area_type_id)
  const sections = areaType?.sections ?? []
  const tab = sections.find((s) => s === params.get('tab')) ?? sections[0]

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>
  if (!area) return <p className="text-sm text-muted-foreground">{T.notFound}</p>

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
    <div className="flex flex-col gap-4">
      <Header area={area} areaType={areaType} areas={areas ?? []} onEdit={() => setEditing(true)} />

      {tab && (
        <Tabs value={tab} onValueChange={setTab}>
          {/* 5–6 вкладок на 360 px не помещаются — прокрутка вбок */}
          <div className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none]">
            <TabsList className="mb-3">
              {sections.map((s) => (
                <TabsTrigger key={s} value={s}>
                  {AREA_SECTION_LABEL[s]}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {sections.map((s) => (
            <TabsContent key={s} value={s}>
              <SectionContent section={s} area={area} />
            </TabsContent>
          ))}
        </Tabs>
      )}

      <AreaDialog
        open={editing}
        onOpenChange={setEditing}
        area={area}
        onDeleted={() => navigate('/areas', { replace: true })}
      />
    </div>
  )
}
