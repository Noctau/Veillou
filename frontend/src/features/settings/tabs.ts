import { BellIcon, CalendarClockIcon, LayoutListIcon, type LucideIcon, PaletteIcon, UserIcon } from 'lucide-react'

/** Вкладки настроек: адрес — `/settings?tab=<id>`, без параметра — первая. */
export type SettingsTab = 'profile' | 'planning' | 'catalog' | 'notifications' | 'interface'

export const SETTINGS_TABS: { id: SettingsTab; label: string; icon: LucideIcon; description: string }[] = [
  { id: 'profile', label: 'Профиль', icon: UserIcon, description: 'О себе для ИИ, аккаунт и пароль.' },
  {
    id: 'planning',
    label: 'Планирование',
    icon: CalendarClockIcon,
    description: 'Сроки, режимы дня, отдых, лимиты нагрузки и калибровка оценок.',
  },
  {
    id: 'catalog',
    label: 'Справочники',
    icon: LayoutListIcon,
    description: 'Типы сфер, занятости, действий и задач, категории, готовые наборы.',
  },
  {
    id: 'notifications',
    label: 'Уведомления',
    icon: BellIcon,
    description: 'Напоминания, сводки и разборы, push и Telegram.',
  },
  { id: 'interface', label: 'Интерфейс', icon: PaletteIcon, description: 'Меню и проверка правописания.' },
]

export function tabFromParam(value: string | null): SettingsTab {
  return SETTINGS_TABS.find((t) => t.id === value)?.id ?? SETTINGS_TABS[0].id
}
