import { ChevronDownIcon, ChevronUpIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryIcon } from '@/features/catalog/CategoryIcon'
import { paletteColor } from '@/lib/colors'
import { errorMessage } from '@/lib/errors'
import { AREAS_UI as T } from '@/lib/terms'
import { cn } from '@/lib/utils'

import { AreaDialog } from './AreaDialog'
import { AreaTypeDialog } from './AreaTypesSection'
import { FieldValuesView } from './FieldValuesView'
import { type Area, type AreaType, useAreas, useAreaTypes } from './useAreas'

function AreaCard({ area, areaType, areas }: { area: Area; areaType?: AreaType; areas: Area[] }) {
  const color = paletteColor(area.color)
  return (
    <Card className={cn('relative overflow-hidden py-0', area.archived_at && 'opacity-70')}>
      <span className={cn('absolute inset-y-0 left-0 w-1.5', color.bg)} aria-hidden />
      <CardContent className="flex flex-col gap-2 py-3 pl-5">
        <Link to={`/areas/${area.id}`} className="flex flex-col text-left after:absolute after:inset-0">
          <span className="font-medium leading-tight">{area.name}</span>
          {area.short_name && <span className="text-xs text-muted-foreground">{area.short_name}</span>}
        </Link>
        {areaType && <FieldValuesView defs={areaType.fields} values={area.fields} areas={areas} className="text-xs" />}
      </CardContent>
    </Card>
  )
}

function TypeGroup({
  areaType,
  areas,
  all,
  periodId,
}: {
  areaType: AreaType
  areas: Area[]
  all: Area[]
  periodId?: string
}) {
  const [creating, setCreating] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const live = areas.filter((a) => !a.archived_at)
  const archived = areas.filter((a) => a.archived_at)
  return (
    <section className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <CategoryIcon name={areaType.icon} className="size-4" />
        {areaType.name_plural}
      </h2>
      {live.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {live.map((a) => (
            <AreaCard key={a.id} area={a} areaType={areaType} areas={all} />
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => setCreating(true)}>
          <PlusIcon /> {areaType.name}
        </Button>
        {archived.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? <ChevronUpIcon /> : <ChevronDownIcon />} {T.archived}: {archived.length}
          </Button>
        )}
      </div>
      {showArchived && (
        <div className="grid gap-3 sm:grid-cols-2">
          {archived.map((a) => (
            <AreaCard key={a.id} area={a} areaType={areaType} areas={all} />
          ))}
        </div>
      )}
      <AreaDialog
        open={creating}
        onOpenChange={setCreating}
        areaTypeId={areaType.id}
        // Период по умолчанию — если сферы этого типа живут по периодам (предметы по семестрам)
        periodId={areas.some((a) => a.period_id) ? periodId : undefined}
        colorIndex={all.length}
      />
    </section>
  )
}

/** Сферы по типам. `periodId` — текущий период: сферы других периодов не показываются. */
export function AreaList({ periodId }: { periodId?: string }) {
  const { data, isPending, isError, error } = useAreas()
  const { data: types, isPending: typesPending } = useAreaTypes()
  const [creatingType, setCreatingType] = useState(false)

  const all = data ?? []
  const visible = all.filter((a) => !periodId || !a.period_id || a.period_id === periodId)

  return (
    <div className="flex flex-col gap-6">
      {(isPending || typesPending) && <Skeleton className="h-24" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {types && types.length === 0 && (
        <div className="flex flex-col items-start gap-3 py-4">
          <p className="text-sm text-muted-foreground">{T.empty}</p>
          <p className="text-sm text-muted-foreground">{T.noTypes}</p>
          <Button variant="outline" onClick={() => setCreatingType(true)}>
            <PlusIcon /> {T.addType}
          </Button>
        </div>
      )}
      {data &&
        types?.map((t) => (
          <TypeGroup
            key={t.id}
            areaType={t}
            areas={visible.filter((a) => a.area_type_id === t.id)}
            all={all}
            periodId={periodId}
          />
        ))}
      <AreaTypeDialog open={creatingType} onOpenChange={setCreatingType} />
    </div>
  )
}
