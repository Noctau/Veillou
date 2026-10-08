import { RotateCcwIcon } from 'lucide-react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useActionTypes } from '@/features/catalog/useCatalog'
import { TASK_TYPE_LABEL } from '@/features/tasks/labels'

import { plural } from './labels'
import { useCalibration, useResetCalibration } from './usePlan'

/** «×1,15» → «на 15% дольше», «×0,9» → «на 10% быстрее». */
function describe(coef: number): string {
  const pct = Math.round((coef - 1) * 100)
  if (pct === 0) return 'как оценено'
  return pct > 0 ? `на ${pct}% дольше` : `на ${-pct}% быстрее`
}

/** Калибровка оценок (M9.4): по отметкам «быстрее / как думала / дольше» на «сделано». */
export function CalibrationSection() {
  const { data: rows, isPending } = useCalibration()
  const { data: types } = useActionTypes()
  const reset = useResetCalibration()
  const typeName = new Map(types?.map((t) => [t.key, t.name]))

  return (
    <Card>
      <CardHeader>
        <CardTitle>Калибровка оценок</CardTitle>
        <CardDescription>
          После «сделано» можно отметить, быстрее или дольше вышло. План учитывает это и умножает оценки шагов на
          коэффициент — отдельно для каждого типа задания и действия.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pt-2">
        {isPending && <Skeleton className="h-16" />}
        {rows && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">Пока отметок нет — оценки берутся как есть.</p>
        )}
        {rows && rows.length > 0 && (
          <>
            <ul className="flex flex-col gap-1.5">
              {rows.map((r) => (
                <li key={`${r.task_type}-${r.action_type}`} className="flex items-baseline gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">
                    {TASK_TYPE_LABEL[r.task_type]} · {typeName.get(r.action_type) ?? r.action_type}
                  </span>
                  <span className="font-medium tabular-nums">×{r.coef.toFixed(2).replace('.', ',')}</span>
                  <span className="w-36 text-right text-xs text-muted-foreground">
                    {describe(r.coef)}, {r.samples} {plural(r.samples, 'отметка', 'отметки', 'отметок')}
                  </span>
                </li>
              ))}
            </ul>
            <ConfirmButton
              title="Сбросить калибровку?"
              description="Все коэффициенты станут 1, прошлые отметки больше не будут учитываться."
              confirmLabel="Сбросить"
              onConfirm={() => reset.mutate()}
            >
              <Button variant="outline" size="sm" className="self-end" disabled={reset.isPending}>
                <RotateCcwIcon /> Сбросить
              </Button>
            </ConfirmButton>
          </>
        )}
      </CardContent>
    </Card>
  )
}
