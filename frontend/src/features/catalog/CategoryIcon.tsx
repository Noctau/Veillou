import { TagIcon, type LucideProps } from 'lucide-react'

import { CATEGORY_ICONS } from './icons'
import type { CategoryIconName } from './useCatalog'

export function CategoryIcon({ name, ...props }: { name: CategoryIconName } & LucideProps) {
  const Icon = CATEGORY_ICONS[name] ?? TagIcon
  return <Icon {...props} />
}
