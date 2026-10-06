import {
  BriefcaseIcon,
  DumbbellIcon,
  FileTextIcon,
  GraduationCapIcon,
  HeartIcon,
  HouseIcon,
  PlaneIcon,
  ShoppingCartIcon,
  StarIcon,
  StethoscopeIcon,
  TagIcon,
  UsersIcon,
  type LucideIcon,
} from 'lucide-react'

import type { CategoryIconName } from './useCatalog'

export const CATEGORY_ICONS: Record<CategoryIconName, LucideIcon> = {
  'graduation-cap': GraduationCapIcon,
  briefcase: BriefcaseIcon,
  house: HouseIcon,
  heart: HeartIcon,
  'shopping-cart': ShoppingCartIcon,
  stethoscope: StethoscopeIcon,
  'file-text': FileTextIcon,
  dumbbell: DumbbellIcon,
  users: UsersIcon,
  plane: PlaneIcon,
  star: StarIcon,
  tag: TagIcon,
}
