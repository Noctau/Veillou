import { PlusIcon, Settings2Icon } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useAreas } from '@/features/areas/useAreas'
import { byId } from '@/features/catalog/useCatalog'
import { errorMessage } from '@/lib/errors'
import { SCHEDULE_UI as T } from '@/lib/terms'
import { isoWeekday, WEEKDAYS_SHORT } from '@/lib/time'

import { cycleWeek as cycleWeekOf } from './cycle'
import { DaysOffEditor } from './DaysOffEditor'
import { describePattern, ruleLabel } from './pattern'
import { PeriodForm } from './PeriodForm'
import { type RuleDraft, ScheduleRuleDialog } from './ScheduleRuleDialog'
import { SlotGridEditor } from './SlotGridEditor'
import { NO_PERIOD, useCurrentPeriod } from './useCurrentPeriod'
import {
  groupGrids,
  type Period,
  type ScheduleRule,
  slotsFor,
  useEventTypes,
  useScheduleRules,
  useSlotGrids,
} from './useSchedule'
import { WeekGrid } from './WeekGrid'

function PeriodSettingsDialog({
  open,
  onOpenChange,
  period,
  today,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  period: Period
  today: string
}) {
  const { data: rows = [] } = useSlotGrids()
  const grids = groupGrids(rows).filter((g) => g.period_id === period.id)
  const [adding, setAdding] = useState(false)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{period.name}</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="slots">
          <TabsList className="mb-3">
            <TabsTrigger value="slots">{T.slots}</TabsTrigger>
            <TabsTrigger value="days-off">{T.daysOff}</TabsTrigger>
            <TabsTrigger value="period">{T.dates}</TabsTrigger>
          </TabsList>
          <TabsContent value="slots" className="flex flex-col gap-6">
            <p className="text-sm text-muted-foreground">{T.slotsHint}</p>
            {grids.map((g) => (
              <SlotGridEditor key={g.id} grid={g} periodId={period.id} />
            ))}
            {grids.length === 0 || adding ? (
              <SlotGridEditor key={`new-${grids.length}`} periodId={period.id} onSaved={() => setAdding(false)} />
            ) : (
              <Button variant="outline" size="sm" className="self-start" onClick={() => setAdding(true)}>
                <PlusIcon /> {T.grid}
              </Button>
            )}
          </TabsContent>
          <TabsContent value="days-off">
            <DaysOffEditor periodId={period.id} />
          </TabsContent>
          <TabsContent value="period">
            <PeriodForm key={period.id} period={period} today={today} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function NewPeriodDialog({
  open,
  onOpenChange,
  today,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  today: string
  onCreated: (p: Period) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{T.newPeriodTitle}</DialogTitle>
        </DialogHeader>
        {open && <PeriodForm today={today} onDone={onCreated} />}
      </DialogContent>
    </Dialog>
  )
}

/** Экран «Расписание»: период, неделя цикла, сетка правил по дням недели, другие повторы. */
export function SchedulePanel() {
  const { period, periods, select, today, isPending, isError, error } = useCurrentPeriod()
  const [creatingPeriod, setCreatingPeriod] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  if (isPending) return <Skeleton className="h-64" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={period?.id ?? NO_PERIOD} onValueChange={select}>
          <SelectTrigger className="w-auto" aria-label={T.period}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {periods.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
            <SelectItem value={NO_PERIOD}>{T.noPeriod}</SelectItem>
          </SelectContent>
        </Select>
        {period && (
          <Button variant="ghost" size="icon" aria-label={T.periodSettings} onClick={() => setSettingsOpen(true)}>
            <Settings2Icon />
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => setCreatingPeriod(true)}>
          <PlusIcon /> {T.newPeriod}
        </Button>
      </div>

      <PeriodSchedule key={period?.id ?? NO_PERIOD} period={period} today={today} />

      <NewPeriodDialog
        open={creatingPeriod}
        onOpenChange={setCreatingPeriod}
        today={today}
        onCreated={(p) => {
          setCreatingPeriod(false)
          select(p.id)
        }}
      />
      {period && (
        <PeriodSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} period={period} today={today} />
      )}
    </div>
  )
}

function PeriodSchedule({ period, today }: { period?: Period; today: string }) {
  const filter = useMemo(() => (period ? { period_id: period.id } : {}), [period])
  const { data: all = [], isPending } = useScheduleRules(filter)
  // Без периода — только правила без периода
  const rules = period ? all : all.filter((r) => !r.period_id)
  const { data: gridRows = [] } = useSlotGrids()
  const { data: allAreas = [] } = useAreas()
  const { data: eventTypes } = useEventTypes()
  const types = byId(eventTypes)
  const areas = useMemo(() => new Map(allAreas.map((a) => [a.id, a])), [allAreas])
  const cycle = period?.cycle_weeks ?? 1
  const currentWeek = period ? cycleWeekOf(today, period) : 1
  const [week, setWeek] = useState(currentWeek)
  const todayWd = isoWeekday(today)
  const [mobileDay, setMobileDay] = useState(todayWd)
  const [dialog, setDialog] = useState<{ rule?: ScheduleRule; draft?: RuleDraft } | null>(null)

  // Сетка экрана: та, по которой идут правила периода, иначе первая сетка периода
  const grids = groupGrids(gridRows).filter((g) => g.period_id === (period?.id ?? null))
  const used = rules.find((r) => r.slot_grid_id)?.slot_grid_id
  const grid = grids.find((g) => g.id === used) ?? grids[0]
  const weekdays = rules.some((r) => r.pattern.kind === 'weekly' && r.pattern.weekdays.includes(7))
    ? [1, 2, 3, 4, 5, 6, 7]
    : [1, 2, 3, 4, 5, 6]
  const others = rules.filter((r) => r.pattern.kind !== 'weekly')

  const gridProps = {
    rules,
    areas,
    types,
    slotsFor: (wd: number) => slotsFor(grid, wd),
    cycleWeek: week,
    onCreate: (weekday: number, slot: number | null) =>
      setDialog({ draft: { weekday, slot: slot ?? undefined, cycleWeek: cycle > 1 ? week : undefined } }),
    onEdit: (rule: ScheduleRule) => setDialog({ rule }),
  }

  return (
    <>
      {!period && <p className="text-sm text-muted-foreground">{T.noPeriodHint}</p>}
      <div className="flex flex-wrap items-center gap-3">
        {cycle > 1 && (
          <>
            <ToggleGroup type="single" variant="outline" value={String(week)} onValueChange={(v) => v && setWeek(Number(v))}>
              {Array.from({ length: cycle }, (_, i) => (
                <ToggleGroupItem key={i} value={String(i + 1)} className="px-3">
                  {T.cycleWeek(i + 1)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <span className="text-sm text-muted-foreground">{T.currentCycleWeek(currentWeek)}</span>
          </>
        )}
        <Button variant="outline" size="sm" className="ml-auto" onClick={() => setDialog({ draft: {} })}>
          <PlusIcon /> {T.addRule}
        </Button>
      </div>

      {isPending ? (
        <Skeleton className="h-64" />
      ) : rules.length === 0 && !grid ? (
        <Card>
          <CardHeader>
            <CardTitle>{T.startTitle}</CardTitle>
            <CardDescription>{T.startHint}</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <Button onClick={() => setDialog({ draft: {} })}>
              <PlusIcon /> {T.addRule}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Телефон: один день */}
          <div className="flex flex-col gap-3 md:hidden">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              className="w-full"
              value={String(mobileDay)}
              onValueChange={(v) => v && setMobileDay(Number(v))}
            >
              {[1, 2, 3, 4, 5, 6, 7].map((wd) => (
                <ToggleGroupItem key={wd} value={String(wd)} className="flex-1">
                  {WEEKDAYS_SHORT[wd - 1]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <WeekGrid {...gridProps} weekdays={[mobileDay]} />
          </div>
          {/* Планшет/ноутбук: вся неделя */}
          <div className="hidden overflow-x-auto md:block">
            <WeekGrid {...gridProps} weekdays={weekdays} />
          </div>
          {period && !grid && <p className="text-sm text-muted-foreground">{T.noGrid}</p>}
        </>
      )}

      {others.length > 0 && (
        <section className="flex flex-col gap-1">
          <h3 className="text-sm font-medium text-muted-foreground">{T.otherRules}</h3>
          {others.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setDialog({ rule: r })}
              className="flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-muted"
            >
              <span className="flex-1 truncate">
                {ruleLabel(r, r.area_id ? areas.get(r.area_id) : undefined, types.get(r.event_type_id))}
              </span>
              <span className="text-muted-foreground">
                {describePattern(r.pattern)}
                {r.start_time && `, ${r.start_time}–${r.end_time}`}
              </span>
            </button>
          ))}
        </section>
      )}

      <ScheduleRuleDialog
        open={!!dialog}
        onOpenChange={(open) => !open && setDialog(null)}
        periodId={period?.id ?? null}
        rule={dialog?.rule}
        draft={dialog?.draft}
        viewCycleWeek={cycle > 1 ? week : undefined}
        onEditRule={(rule) => setDialog({ rule })}
      />
    </>
  )
}
