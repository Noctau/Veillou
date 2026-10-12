import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { paletteColor } from '@/lib/colors'
import { AREAS_UI } from '@/lib/terms'
import { cn } from '@/lib/utils'

import { selectableAreas, useAreas } from './useAreas'

const NONE = 'none'

/** Выбор сферы: живые сферы (текущая — даже из архива) и «Без сферы». */
export function AreaSelect({
  id,
  value,
  onChange,
  emptyLabel = AREAS_UI.noArea,
  className,
}: {
  id?: string
  value: string | null
  onChange: (value: string | null) => void
  emptyLabel?: string
  className?: string
}) {
  const { data } = useAreas()
  const areas = selectableAreas(data, value)
  return (
    <Select value={value ?? NONE} onValueChange={(v) => onChange(v === NONE ? null : v)}>
      <SelectTrigger id={id} className={cn('w-full', className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{emptyLabel}</SelectItem>
        {areas.map((a) => (
          <SelectItem key={a.id} value={a.id}>
            <span className={cn('size-2.5 rounded-full', paletteColor(a.color).bg)} />
            {a.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
