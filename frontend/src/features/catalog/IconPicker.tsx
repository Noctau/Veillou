import { cn } from '@/lib/utils'

import { CategoryIcon } from './CategoryIcon'
import { CATEGORY_ICONS } from './icons'
import type { CategoryIconName } from './useCatalog'

/** Выбор иконки справочника (категории, типы задач). */
export function IconPicker({ value, onChange }: { value: CategoryIconName; onChange: (icon: CategoryIconName) => void }) {
  return (
    <div role="radiogroup" className="flex flex-wrap gap-2">
      {(Object.keys(CATEGORY_ICONS) as CategoryIconName[]).map((key) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          aria-label={key}
          onClick={() => onChange(key)}
          className={cn('flex size-9 items-center justify-center rounded-lg border', value === key && 'border-foreground bg-muted')}
        >
          <CategoryIcon name={key} className="size-4" />
        </button>
      ))}
    </div>
  )
}
