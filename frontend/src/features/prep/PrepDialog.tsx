import { Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useCalendar, useUpdateEvent } from '@/features/calendar/useCalendar'
import { useEventTypes } from '@/features/schedule/useSchedule'
import { PREP_UI as T } from '@/lib/terms'
import { addDaysIso, dayStartUtc, todayIn, wallDate, wallTime, wallToUtc } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'

import {
  type PrepPlan,
  type PrepStrategy,
  useCreatePrepPlan,
  useDeletePrepPlan,
  useUpdatePrepPlan,
} from './usePrep'

type Target = 'new' | 'existing' | 'date'

type Props = {
  areaId?: string
  /** Готовиться к этому событию (из карточки события) — выбор цели не показывается. */
  eventId?: string
  plan?: PrepPlan
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Подготовка: к чему (новое событие, событие из календаря, дата), как и сколько. */
export function PrepDialog({ open, onOpenChange, plan, ...rest }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{plan ? T.editTitle : T.newTitle}</DialogTitle>
        </DialogHeader>
        {open && <PrepForm key={plan?.id ?? 'new'} plan={plan} {...rest} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function num(value: string, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(Number(value) || 0)))
}

function PrepForm({ areaId, eventId, plan, onDone }: Omit<Props, 'open' | 'onOpenChange'> & { onDone: () => void }) {
  const tz = useTimeZone()
  const today = todayIn(tz)
  const create = useCreatePrepPlan()
  const update = useUpdatePrepPlan()
  const remove = useDeletePrepPlan()
  const updateEvent = useUpdateEvent()
  const { data: types = [] } = useEventTypes()
  const prepTypes = types.filter((t) => t.supports_prep)
  const prepTypeIds = new Set(prepTypes.map((t) => t.id))

  const [target, setTarget] = useState<Target>(eventId ? 'existing' : 'new')
  const [typeId, setTypeId] = useState(prepTypes[0]?.id ?? '')
  const [chosenEvent, setChosenEvent] = useState(eventId ?? '')
  const event = plan?.event
  const [date, setDate] = useState(
    event ? wallDate(event.start, tz) : (plan?.date ?? addDaysIso(today, 14)),
  )
  const [time, setTime] = useState(event ? wallTime(event.start, tz) : '10:00')
  const [location, setLocation] = useState(event?.location ?? '')
  const [duration, setDuration] = useState(
    event ? Math.round((Date.parse(event.end) - Date.parse(event.start)) / 60_000) : 180,
  )
  const [title, setTitle] = useState(plan ? plan.title : '')
  const [strategy, setStrategy] = useState<PrepStrategy>(plan?.strategy ?? 'spaced')
  const [days, setDays] = useState(plan?.start_days_before ?? 7)
  const [learn, setLearn] = useState(plan?.learn_min ?? 45)
  const [review, setReview] = useState(plan?.review_min ?? 15)
  const [run, setRun] = useState(plan?.run_min ?? 5)
  const [advanced, setAdvanced] = useState(false)

  // Будущие события с подготовкой (у сферы, если она задана) — для «Событие из календаря»
  const from = dayStartUtc(today, tz)
  const to = dayStartUtc(addDaysIso(today, 365), tz)
  const { data: calendar } = useCalendar(!plan && !eventId && target === 'existing' ? from : undefined, to)
  const candidates = (calendar?.events ?? []).filter(
    (e) =>
      e.kind === 'busy' &&
      e.status !== 'cancelled' &&
      (!areaId || e.area_id === areaId) &&
      e.event_type_id &&
      prepTypeIds.has(e.event_type_id),
  )

  const saving = create.isPending || update.isPending || updateEvent.isPending
  const valid =
    days >= 1 &&
    (target !== 'existing' || !!chosenEvent || !!plan) &&
    (target === 'existing' || plan?.event || /^\d{4}-\d{2}-\d{2}$/.test(date))

  const params = {
    title: title.trim(),
    strategy,
    start_days_before: days,
    learn_min: learn,
    review_min: review,
    run_min: run,
  }

  const save = async () => {
    try {
      if (plan) {
        if (event) {
          const start = wallToUtc(date, time, tz)
          const end = new Date(Date.parse(start) + duration * 60_000).toISOString()
          await updateEvent.mutateAsync({ id: event.id, body: { start, end, location: location.trim() || null } })
        }
        await update.mutateAsync({ id: plan.id, body: { ...params, ...(plan.event ? {} : { date }) } })
      } else if (target === 'existing') {
        await create.mutateAsync({ area_id: areaId ?? null, event_id: chosenEvent, ...params, note: '' })
      } else if (target === 'date') {
        await create.mutateAsync({ area_id: areaId ?? null, date, ...params, note: '' })
      } else {
        await create.mutateAsync({
          area_id: areaId ?? null,
          event: {
            event_type_id: typeId || null,
            title: '',
            start: wallToUtc(date, time, tz),
            duration_min: duration,
            location: location.trim() || null,
          },
          ...params,
          note: '',
        })
      }
      onDone()
    } catch {
      // ошибка уже показана тостом
    }
  }

  const showEventFields = plan ? !!event : target === 'new'
  const showDate = plan ? true : target !== 'existing'

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) void save()
      }}
    >
      <FieldGroup>
        {!plan && !eventId && (
          <Field>
            <FieldLabel>{T.target}</FieldLabel>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              className="flex-wrap justify-start"
              value={target}
              onValueChange={(v) => v && setTarget(v as Target)}
            >
              {(['new', 'existing', 'date'] as const).map((k) => (
                <ToggleGroupItem key={k} value={k} className="px-3">
                  {T.targets[k]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
        )}
        {!plan && target === 'new' && (
          <Field>
            <FieldLabel htmlFor="prep-type">{T.eventType}</FieldLabel>
            {prepTypes.length ? (
              <Select value={typeId} onValueChange={setTypeId}>
                <SelectTrigger id="prep-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {prepTypes.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <FieldDescription>{T.noPrepTypes}</FieldDescription>
            )}
          </Field>
        )}
        {!plan && !eventId && target === 'existing' && (
          <Field>
            <FieldLabel htmlFor="prep-event">{T.event}</FieldLabel>
            {candidates.length ? (
              <Select value={chosenEvent} onValueChange={setChosenEvent}>
                <SelectTrigger id="prep-event" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.title} · {wallDate(e.start, tz)} {wallTime(e.start, tz)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <FieldDescription>{T.noEvents}</FieldDescription>
            )}
          </Field>
        )}
        {showDate && (
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Field>
              <FieldLabel htmlFor="prep-date">{T.date}</FieldLabel>
              <Input id="prep-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            {showEventFields && (
              <Field>
                <FieldLabel htmlFor="prep-time">{T.time}</FieldLabel>
                <Input id="prep-time" type="time" step={300} className="w-28" value={time} onChange={(e) => setTime(e.target.value)} />
              </Field>
            )}
          </div>
        )}
        {showEventFields && (
          <div className="grid grid-cols-2 gap-2">
            <Field>
              <FieldLabel htmlFor="prep-location">{T.location}</FieldLabel>
              <Input id="prep-location" value={location} onChange={(e) => setLocation(e.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="prep-duration">{T.duration}</FieldLabel>
              <Input
                id="prep-duration"
                type="number"
                inputMode="numeric"
                step={15}
                value={duration}
                onChange={(e) => setDuration(num(e.target.value, 15, 600))}
              />
            </Field>
          </div>
        )}
        <Field>
          <FieldLabel>{T.strategy}</FieldLabel>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            className="justify-start"
            value={strategy}
            onValueChange={(v) => v && setStrategy(v as PrepStrategy)}
          >
            {(['spaced', 'even'] as const).map((k) => (
              <ToggleGroupItem key={k} value={k} className="px-3">
                {T.strategies[k]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <FieldDescription>{T.strategyHints[strategy]}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="prep-days">{T.daysBefore}</FieldLabel>
          <Input
            id="prep-days"
            type="number"
            inputMode="numeric"
            className="w-28"
            value={days}
            onChange={(e) => setDays(num(e.target.value, 1, 60))}
          />
        </Field>
        {advanced ? (
          <>
            <Field>
              <FieldLabel>{T.perItem}</FieldLabel>
              <div className="grid grid-cols-3 gap-2">
                <Input aria-label={T.learn} type="number" inputMode="numeric" value={learn} onChange={(e) => setLearn(num(e.target.value, 5, 240))} />
                <Input
                  aria-label={T.review}
                  type="number"
                  inputMode="numeric"
                  disabled={strategy === 'even'}
                  value={review}
                  onChange={(e) => setReview(num(e.target.value, 1, 120))}
                />
                <Input aria-label={T.run} type="number" inputMode="numeric" value={run} onChange={(e) => setRun(num(e.target.value, 0, 60))} />
              </div>
              <FieldDescription>
                {T.learn} / {T.review} / {T.run}. {T.runHint}
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="prep-title">{T.title}</FieldLabel>
              <Input id="prep-title" placeholder={T.titlePlaceholder} value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
          </>
        ) : (
          <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setAdvanced(true)}>
            {T.timeChip(learn, review, run)}
          </Button>
        )}
      </FieldGroup>
      <DialogFooter className="flex-row flex-wrap items-center gap-2">
        {plan && (
          <ConfirmButton
            title={T.deleteTitle}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate({ id: plan.id, withEvent: false }, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        {plan?.event && (
          <ConfirmButton
            title={T.deleteTitle}
            description={T.deleteWithEvent}
            onConfirm={() => remove.mutate({ id: plan.id, withEvent: true }, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="sm" className="text-destructive">
              {T.deleteWithEvent}
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" className="ml-auto" disabled={!valid || saving}>
          {T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
