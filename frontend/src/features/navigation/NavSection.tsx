import { ArrowDownIcon, ArrowUpIcon, PlusIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { buildNav, SECTION_NAV } from '@/components/layout/nav'
import { useAreas, useAreaTypes } from '@/features/areas/useAreas'
import { useUpdateSettings, type UserSettings } from '@/features/settings/useSettings'
import { NAV_UI as T } from '@/lib/terms'

const MAX_NAV = 6
const CARDS = Object.keys(T.cards)

function ItemButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}>
      <PlusIcon /> {label}
    </Button>
  )
}

/** Настройки → «Навигация»: вкладки после закреплённых и карточки «Сегодня» (M22.2). */
export function NavSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const { data: areaTypes = [] } = useAreaTypes()
  const { data: areas = [] } = useAreas()
  const live = areas.filter((a) => !a.archived_at)
  const chosen = buildNav(settings.nav, areaTypes, areas)
  const keys = chosen.map((i) => i.key!)
  const full = keys.length >= MAX_NAV

  const save = (nav: string[]) => update.mutate({ nav })
  const move = (i: number, d: number) => {
    const next = [...keys]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    save(next)
  }
  const add = (key: string) => save([...keys, key])
  const cards = new Set<string>(settings.today_cards)
  const toggleCard = (card: string, on: boolean) =>
    update.mutate({
      today_cards: CARDS.filter((c) => (c === card ? on : cards.has(c))) as UserSettings['today_cards'],
    })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{T.sectionTitle}</CardTitle>
        <CardDescription>{T.sectionDescription}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 pt-2">
        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium">{T.chosen}</div>
          {chosen.length === 0 && <p className="text-sm text-muted-foreground">{T.none}</p>}
          <ul className="flex flex-col gap-1">
            {chosen.map((item, i) => {
              const Icon = item.icon
              return (
                <li key={item.key} className="flex items-center gap-2 rounded-lg border px-3 py-1.5">
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="flex-1 text-sm">{item.label}</span>
                  <Button variant="ghost" size="icon" aria-label={T.up} disabled={i === 0} onClick={() => move(i, -1)}>
                    <ArrowUpIcon />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={T.down}
                    disabled={i === chosen.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    <ArrowDownIcon />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={T.remove} onClick={() => save(keys.filter((k) => k !== item.key))}>
                    <XIcon />
                  </Button>
                </li>
              )
            })}
          </ul>
        </div>
        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium">{full ? T.limit(MAX_NAV) : T.available}</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(SECTION_NAV)
              .filter(([key]) => !keys.includes(key))
              .map(([key, item]) => (
                <ItemButton key={key} label={item.label} disabled={full} onClick={() => add(key)} />
              ))}
          </div>
          {areaTypes.some((t) => !keys.includes(`area_type:${t.id}`)) && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">{T.areaTypes}:</span>
              {areaTypes
                .filter((t) => !keys.includes(`area_type:${t.id}`))
                .map((t) => (
                  <ItemButton key={t.id} label={t.name_plural} disabled={full} onClick={() => add(`area_type:${t.id}`)} />
                ))}
            </div>
          )}
          {live.some((a) => !keys.includes(`area:${a.id}`)) && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">{T.areaItems}:</span>
              {live
                .filter((a) => !keys.includes(`area:${a.id}`))
                .map((a) => (
                  <ItemButton key={a.id} label={a.short_name || a.name} disabled={full} onClick={() => add(`area:${a.id}`)} />
                ))}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium">{T.todayTitle}</div>
          {CARDS.map((card) => (
            <Field key={card} orientation="horizontal">
              <Switch id={`card-${card}`} checked={cards.has(card)} onCheckedChange={(on) => toggleCard(card, on)} />
              <FieldLabel htmlFor={`card-${card}`}>{T.cards[card]}</FieldLabel>
            </Field>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
