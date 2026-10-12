import { ChevronDownIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { DAY_PROFILES_UI as T } from '@/lib/terms'

import { useDayProfileDays, useDayProfiles, useSetDayProfile } from './useDayProfiles'

const BY_RULES = '__rules__'

/** Режим дня на «Сегодня»: «сегодня выходной» — одно касание (правило на эту дату). */
export function TodayProfileChip({ day }: { day: string }) {
  const { data: profiles = [] } = useDayProfiles()
  const { data: days } = useDayProfileDays(day, day)
  const set = useSetDayProfile()
  const current = days?.[0]
  if (!current || profiles.length === 0) return null
  const value = current.pinned ? (current.profile_id ?? BY_RULES) : BY_RULES

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 rounded-full px-3 text-xs" aria-label={T.today}>
          {current.name}
          <ChevronDownIcon className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-52">
        <DropdownMenuLabel>{T.today}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(v) => set.mutate({ day, profileId: v === BY_RULES ? null : v })}
        >
          {profiles.map((p) => (
            <DropdownMenuRadioItem key={p.id} value={p.id}>
              {p.name}
            </DropdownMenuRadioItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuRadioItem value={BY_RULES}>{T.byRules}</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <p className="px-2 py-1 text-xs text-muted-foreground">{T.todayHint}</p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
