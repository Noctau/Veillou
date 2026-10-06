import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import { CategoryIcon } from './CategoryIcon'
import { useActionTypes, useCategories } from './useCatalog'

const NONE = 'none'

type Props = {
  id?: string
  value: string | null | undefined
  onChange: (id: string | null) => void
  /** Подпись пустого значения. */
  emptyLabel?: string
}

export function CategorySelect({ id, value, onChange, emptyLabel = 'Без категории' }: Props) {
  const { data: categories } = useCategories()
  return (
    <Select value={value ?? NONE} onValueChange={(v) => onChange(v === NONE ? null : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{emptyLabel}</SelectItem>
        {categories?.map((c) => (
          <SelectItem key={c.id} value={c.id}>
            <CategoryIcon name={c.icon} className="size-4" />
            {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function ActionTypeSelect({ id, value, onChange, emptyLabel = 'Не задан' }: Props) {
  const { data: types } = useActionTypes()
  return (
    <Select value={value ?? NONE} onValueChange={(v) => onChange(v === NONE ? null : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{emptyLabel}</SelectItem>
        {types?.map((t) => (
          <SelectItem key={t.id} value={t.id}>
            {t.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
