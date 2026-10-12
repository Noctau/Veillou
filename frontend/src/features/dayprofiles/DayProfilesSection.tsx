import { ChevronDownIcon, ChevronUpIcon, PlusIcon, Trash2Icon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldContent, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { byId } from '@/features/catalog/useCatalog'
import { useEventTypes } from '@/features/schedule/useSchedule'
import { DAY_PROFILES_UI as T } from '@/lib/terms'
import { WEEKDAYS_SHORT } from '@/lib/time'

import {
  type DayProfile,
  type DayProfileCreate,
  type DayProfileRule,
  type DayRuleKind,
  useCreateDayProfile,
  useCreateDayRule,
  useDayProfileRules,
  useDayProfiles,
  useDeleteDayProfile,
  useDeleteDayRule,
  useUpdateDayProfile,
} from './useDayProfiles'

type Span = { start: string; end: string }

function weekdaysText(days: number[]): string {
  return days.map((d) => WEEKDAYS_SHORT[d - 1]).join(', ')
}

function fmtDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}

function ruleText(rule: DayProfileRule, eventTypeName: (id: string) => string): string {
  switch (rule.kind) {
    case 'weekdays':
      return T.ruleText.weekdays(weekdaysText(rule.weekdays))
    case 'dates':
      return T.ruleText.dates(fmtDate(rule.date_from ?? ''), fmtDate(rule.date_to ?? rule.date_from ?? ''))
    case 'event_day':
      return T.ruleText.event_day(eventTypeName(rule.event_type_id ?? ''))
    case 'day_after':
      return T.ruleText.day_after(eventTypeName(rule.event_type_id ?? ''))
  }
}

function Flag({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <Field orientation="horizontal">
      <FieldContent>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <FieldDescription>{hint}</FieldDescription>
      </FieldContent>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </Field>
  )
}

function SpanInput({ value, onChange, label }: { value: Span; onChange: (v: Span) => void; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <Input
        type="time"
        step={300}
        aria-label={`${label}: с`}
        value={value.start}
        onChange={(e) => onChange({ ...value, start: e.target.value })}
      />
      <span className="text-muted-foreground">—</span>
      <Input
        type="time"
        step={300}
        aria-label={`${label}: до`}
        value={value.end}
        onChange={(e) => onChange({ ...value, end: e.target.value })}
      />
    </div>
  )
}

/** Редактор режима: базовое сразу, флаги отдыха и тихих часов — под «Подробнее». */
function ProfileForm({ profile, onDone }: { profile?: DayProfile; onDone: () => void }) {
  const create = useCreateDayProfile()
  const update = useUpdateDayProfile()
  const remove = useDeleteDayProfile()
  const [name, setName] = useState(profile?.name ?? '')
  const [wake, setWake] = useState(profile?.wake ?? '07:30')
  const [sleep, setSleep] = useState(profile?.sleep ?? '23:30')
  const [lunch, setLunch] = useState<Span | null>(profile ? profile.lunch : { start: '13:00', end: '14:00' })
  const [work, setWork] = useState<Span[]>(profile?.work_windows ?? [{ start: '09:00', end: '21:00' }])
  const [evening, setEvening] = useState(profile?.rest_evening_ok ?? true)
  const [halfday, setHalfday] = useState(profile?.rest_halfday_ok ?? false)
  const [quiet, setQuiet] = useState(profile?.quiet_follows_sleep ?? true)
  const [more, setMore] = useState(false)
  const saving = create.isPending || update.isPending
  const valid =
    name.trim() !== '' &&
    wake !== '' &&
    sleep !== '' &&
    wake !== sleep &&
    (lunch === null || (lunch.start !== '' && lunch.end > lunch.start)) &&
    work.every((w) => w.start !== '' && w.end !== '' && w.start !== w.end)

  const save = () => {
    const body: DayProfileCreate = {
      name: name.trim(),
      wake,
      sleep,
      lunch,
      work_windows: work,
      rest_evening_ok: evening,
      rest_halfday_ok: halfday,
      quiet_follows_sleep: quiet,
    }
    if (profile) update.mutate({ id: profile.id, body }, { onSuccess: onDone })
    else create.mutate(body, { onSuccess: onDone })
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="dp-name">{T.name}</FieldLabel>
        <Input
          id="dp-name"
          autoFocus={!profile}
          placeholder={T.namePlaceholder}
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-4">
        <Field className="w-auto">
          <FieldLabel htmlFor="dp-wake">{T.wake}</FieldLabel>
          <Input id="dp-wake" type="time" step={300} value={wake} onChange={(e) => setWake(e.target.value)} />
        </Field>
        <Field className="w-auto">
          <FieldLabel htmlFor="dp-sleep">{T.sleep}</FieldLabel>
          <Input id="dp-sleep" type="time" step={300} value={sleep} onChange={(e) => setSleep(e.target.value)} />
        </Field>
      </div>
      <FieldDescription className="-mt-3">{T.sleepHint}</FieldDescription>
      <Field>
        <FieldLabel>{T.work}</FieldLabel>
        <div className="flex flex-col gap-2">
          {work.map((w, i) => (
            <div key={i} className="flex items-center gap-1">
              <SpanInput
                label={T.work}
                value={w}
                onChange={(v) => setWork(work.map((x, j) => (j === i ? v : x)))}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={T.removeWindow}
                onClick={() => setWork(work.filter((_, j) => j !== i))}
              >
                <XIcon />
              </Button>
            </div>
          ))}
          {work.length < 6 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => setWork([...work, { start: '09:00', end: '18:00' }])}
            >
              <PlusIcon /> {T.addWindow}
            </Button>
          )}
        </div>
        <FieldDescription>{T.workHint}</FieldDescription>
      </Field>
      <Field>
        <FieldLabel>{T.lunch}</FieldLabel>
        <div className="flex flex-wrap items-center gap-3">
          {lunch && <SpanInput label={T.lunch} value={lunch} onChange={setLunch} />}
          <div className="flex items-center gap-2">
            <Checkbox
              id="dp-no-lunch"
              checked={lunch === null}
              onCheckedChange={(v) => setLunch(v === true ? null : { start: '13:00', end: '14:00' })}
            />
            <FieldLabel htmlFor="dp-no-lunch" className="font-normal">
              {T.noLunch}
            </FieldLabel>
          </div>
        </div>
      </Field>

      <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setMore(!more)}>
        {more ? <ChevronUpIcon /> : <ChevronDownIcon />} {more ? T.less : T.more}
      </Button>
      {more && (
        <div className="flex flex-col gap-5">
          <Flag id="dp-evening" label={T.restEvening} hint={T.restEveningHint} checked={evening} onChange={setEvening} />
          <Flag id="dp-halfday" label={T.restHalfday} hint={T.restHalfdayHint} checked={halfday} onChange={setHalfday} />
          <Flag id="dp-quiet" label={T.quiet} hint={T.quietHint} checked={quiet} onChange={setQuiet} />
        </div>
      )}

      <DialogFooter className="flex-row items-center">
        {profile && (
          <ConfirmButton
            title={T.deleteTitle(profile.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(profile.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" className="ml-auto" disabled={!valid || saving}>
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}

const KINDS: DayRuleKind[] = ['weekdays', 'dates', 'event_day', 'day_after']

function RuleForm({ profiles, onDone }: { profiles: DayProfile[]; onDone: () => void }) {
  const create = useCreateDayRule()
  const { data: eventTypes = [] } = useEventTypes()
  const [kind, setKind] = useState<DayRuleKind>('weekdays')
  const [profileId, setProfileId] = useState(profiles[0]?.id ?? '')
  const [weekdays, setWeekdays] = useState<string[]>([])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [eventTypeId, setEventTypeId] = useState(eventTypes[0]?.id ?? '')
  const byEvent = kind === 'event_day' || kind === 'day_after'
  const valid =
    profileId !== '' &&
    (kind !== 'weekdays' || weekdays.length > 0) &&
    (kind !== 'dates' || (from !== '' && (to === '' || to >= from))) &&
    (!byEvent || eventTypeId !== '')

  const save = () =>
    create.mutate(
      {
        profile_id: profileId,
        kind,
        weekdays: kind === 'weekdays' ? weekdays.map(Number) : [],
        date_from: kind === 'dates' ? from : null,
        date_to: kind === 'dates' ? to || from : null,
        event_type_id: byEvent ? eventTypeId : null,
      },
      { onSuccess: onDone },
    )

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <Field>
        <FieldLabel>{T.ruleKind}</FieldLabel>
        <Select value={kind} onValueChange={(v) => setKind(v as DayRuleKind)}>
          <SelectTrigger aria-label={T.ruleKind}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((k) => (
              <SelectItem key={k} value={k}>
                {T.kinds[k]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {kind === 'weekdays' && (
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          className="flex-wrap justify-start"
          value={weekdays}
          onValueChange={setWeekdays}
        >
          {WEEKDAYS_SHORT.map((d, i) => (
            <ToggleGroupItem key={d} value={String(i + 1)} className="px-3">
              {d}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
      {kind === 'dates' && (
        <div className="flex flex-wrap gap-4">
          <Field className="w-auto">
            <FieldLabel htmlFor="dr-from">{T.ruleFrom}</FieldLabel>
            <Input id="dr-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field className="w-auto">
            <FieldLabel htmlFor="dr-to">{T.ruleTo}</FieldLabel>
            <Input id="dr-to" type="date" min={from} value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      )}
      {byEvent &&
        (eventTypes.length ? (
          <Field>
            <FieldLabel>{T.ruleEventType}</FieldLabel>
            <Select value={eventTypeId} onValueChange={setEventTypeId}>
              <SelectTrigger aria-label={T.ruleEventType}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {eventTypes.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        ) : (
          <p className="text-sm text-muted-foreground">{T.noEventTypes}</p>
        ))}
      <Field>
        <FieldLabel>{T.ruleProfile}</FieldLabel>
        <Select value={profileId} onValueChange={setProfileId}>
          <SelectTrigger aria-label={T.ruleProfile}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {profiles.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={!valid || create.isPending}>
          {create.isPending ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}

/** Настройки → «Режимы дня» (M18.3): режимы и правила, какой режим у какого дня. */
export function DayProfilesSection() {
  const { data: profiles, isPending } = useDayProfiles()
  const { data: rules = [] } = useDayProfileRules()
  const eventTypes = byId(useEventTypes().data)
  const removeRule = useDeleteDayRule()
  const [editing, setEditing] = useState<{ profile?: DayProfile } | null>(null)
  const [addingRule, setAddingRule] = useState(false)
  const profileName = new Map((profiles ?? []).map((p) => [p.id, p.name]))
  const typeName = (id: string) => eventTypes.get(id)?.name ?? '—'

  return (
    <Card>
      <CardHeader>
        <CardTitle>{T.title}</CardTitle>
        <CardDescription>{T.description}</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={() => setEditing({})}>
            <PlusIcon /> {T.add}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pt-2">
        {isPending && <Skeleton className="h-16" />}
        {profiles && profiles.length === 0 && <p className="text-sm text-muted-foreground">{T.empty}</p>}
        <ul className="flex flex-col">
          {profiles?.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => setEditing({ profile: p })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{p.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[T.summary(p.wake, p.sleep), p.work_windows.map((w) => `${w.start}–${w.end}`).join(', ')]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
        {!!profiles?.length && (
          <>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{T.rules}</div>
                <p className="text-xs text-muted-foreground">{T.rulesHint}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setAddingRule(true)}>
                <PlusIcon /> {T.addRule}
              </Button>
            </div>
            <ul className="flex flex-col">
              {rules.map((r) => (
                <li key={r.id} className="flex items-center gap-2 px-2 py-1 text-sm">
                  <span className="min-w-0 flex-1 truncate">{ruleText(r, typeName)}</span>
                  <span className="shrink-0 text-muted-foreground">→ {profileName.get(r.profile_id)}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={T.removeRule}
                    onClick={() => removeRule.mutate(r.id)}
                  >
                    <XIcon />
                  </Button>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing?.profile?.name ?? T.newTitle}</DialogTitle>
          </DialogHeader>
          {editing && (
            <ProfileForm key={editing.profile?.id ?? 'new'} profile={editing.profile} onDone={() => setEditing(null)} />
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={addingRule} onOpenChange={setAddingRule}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{T.newRule}</DialogTitle>
          </DialogHeader>
          {addingRule && profiles && <RuleForm profiles={profiles} onDone={() => setAddingRule(false)} />}
        </DialogContent>
      </Dialog>
    </Card>
  )
}
