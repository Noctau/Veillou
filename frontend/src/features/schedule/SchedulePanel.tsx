import { PlusIcon, Settings2Icon } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useSubjects } from '@/features/subjects/useSubjects'
import { errorMessage } from '@/lib/errors'
import { isoWeekday, WEEKDAYS_SHORT } from '@/lib/time'

import { BellsEditor } from './BellsEditor'
import { ClassRuleDialog, type RuleDraft } from './ClassRuleDialog'
import { DaysOffEditor } from './DaysOffEditor'
import { PARITY_LABEL, weekParity } from './parity'
import { SemesterForm } from './SemesterForm'
import { useCurrentSemester } from './useCurrentSemester'
import { type BellSlot, type ClassRule, type Parity, type Semester, useBells, useClassRules } from './useSchedule'
import { WeekGrid } from './WeekGrid'

function SemesterSettingsDialog({
  open,
  onOpenChange,
  semester,
  today,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  semester: Semester
  today: string
}) {
  const { data: bells } = useBells(semester.id)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{semester.name}</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="bells">
          <TabsList className="mb-3">
            <TabsTrigger value="bells">Звонки</TabsTrigger>
            <TabsTrigger value="days-off">Выходные</TabsTrigger>
            <TabsTrigger value="semester">Даты</TabsTrigger>
          </TabsList>
          <TabsContent value="bells">
            {bells ? <BellsEditor key={semester.id} semesterId={semester.id} bells={bells} /> : <Skeleton className="h-40" />}
          </TabsContent>
          <TabsContent value="days-off">
            <DaysOffEditor />
          </TabsContent>
          <TabsContent value="semester">
            <SemesterForm key={semester.id} semester={semester} today={today} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function NewSemesterDialog({ open, onOpenChange, today, onCreated }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  today: string
  onCreated: (s: Semester) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Новый семестр</DialogTitle>
        </DialogHeader>
        {open && <SemesterForm today={today} onDone={onCreated} />}
      </DialogContent>
    </Dialog>
  )
}

export function SchedulePanel() {
  const { semester, semesters, select, today, isPending, isError, error } = useCurrentSemester()
  const [creatingSemester, setCreatingSemester] = useState(false)

  if (isPending) return <Skeleton className="h-64" />
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  if (!semester) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Начнём с семестра</CardTitle>
          <CardDescription>
            Даты занятий и сессии. Звонки подставим стандартные — их можно поправить.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <SemesterForm today={today} onDone={(s) => select(s.id)} />
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <SemesterSchedule
        semester={semester}
        semesters={semesters}
        today={today}
        onSelect={select}
        onNewSemester={() => setCreatingSemester(true)}
      />
      <NewSemesterDialog
        open={creatingSemester}
        onOpenChange={setCreatingSemester}
        today={today}
        onCreated={(s) => {
          setCreatingSemester(false)
          select(s.id)
        }}
      />
    </>
  )
}

function SemesterSchedule({
  semester,
  semesters,
  today,
  onSelect,
  onNewSemester,
}: {
  semester: Semester
  semesters: Semester[]
  today: string
  onSelect: (id: string) => void
  onNewSemester: () => void
}) {
  const { data: bells = [] } = useBells(semester.id)
  const { data: rules = [], isPending } = useClassRules(semester.id)
  const { data: allSubjects = [] } = useSubjects()
  const currentParity = weekParity(today, semester.start_date, semester.first_week_parity)
  const [parity, setParity] = useState<Parity>(currentParity)
  const todayWd = isoWeekday(today)
  const [mobileDay, setMobileDay] = useState(todayWd === 7 ? 1 : todayWd)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [dialog, setDialog] = useState<{ rule?: ClassRule; draft?: RuleDraft } | null>(null)

  const subjects = useMemo(
    () => allSubjects.filter((s) => s.semester_id === semester.id || !s.semester_id),
    [allSubjects, semester.id],
  )
  const subjectMap = useMemo(() => new Map(allSubjects.map((s) => [s.id, s])), [allSubjects])

  const bellsFor = (weekday: number): BellSlot[] =>
    (bells.find((b) => b.weekday === weekday) ?? bells.find((b) => b.weekday === null))?.slots ?? []

  const weekdays = rules.some((r) => r.weekday === 7) ? [1, 2, 3, 4, 5, 6, 7] : [1, 2, 3, 4, 5, 6]
  const gridProps = {
    rules,
    subjects: subjectMap,
    bellsFor,
    parity,
    onCreate: (weekday: number, pair_number: number | null) =>
      setDialog({ draft: { weekday, pair_number } }),
    onEdit: (rule: ClassRule) => setDialog({ rule }),
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {semesters.length > 1 ? (
          <Select value={semester.id} onValueChange={onSelect}>
            <SelectTrigger className="w-auto">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {semesters.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span className="font-medium">{semester.name}</span>
        )}
        <Button variant="ghost" size="icon" aria-label="Настройки семестра" onClick={() => setSettingsOpen(true)}>
          <Settings2Icon />
        </Button>
        <Button variant="ghost" size="sm" onClick={onNewSemester}>
          <PlusIcon /> Семестр
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <ToggleGroup type="single" variant="outline" value={parity} onValueChange={(v) => v && setParity(v as Parity)}>
          {(['odd', 'even'] as Parity[]).map((p) => (
            <ToggleGroupItem key={p} value={p}>
              {PARITY_LABEL[p]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="text-sm text-muted-foreground">
          Сейчас {PARITY_LABEL[currentParity].toLowerCase()}
        </span>
      </div>

      {isPending ? (
        <Skeleton className="h-64" />
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
              {weekdays.map((wd) => (
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
        </>
      )}

      {bells.length === 0 && !isPending && (
        <p className="text-sm text-muted-foreground">
          Звонки не заданы — откройте настройки семестра.
        </p>
      )}

      <ClassRuleDialog
        open={!!dialog}
        onOpenChange={(open) => !open && setDialog(null)}
        semesterId={semester.id}
        subjects={subjects}
        bellsFor={bellsFor}
        rule={dialog?.rule}
        draft={dialog?.draft}
        viewParity={parity}
        onEditRule={(rule) => setDialog({ rule })}
      />
      <SemesterSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} semester={semester} today={today} />
    </div>
  )
}
