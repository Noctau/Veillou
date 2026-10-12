import { useState } from 'react'

import { ColorPicker } from '@/components/common/ColorPicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { AreaSelect } from '@/features/areas/AreaSelect'
import { compactValues } from '@/features/areas/fields'
import { FieldValuesForm } from '@/features/areas/FieldValuesForm'
import { type FieldValues, useAreas } from '@/features/areas/useAreas'
import { useCreateScheduleRule, useEventTypes } from '@/features/schedule/useSchedule'
import { paletteColor } from '@/lib/colors'
import { EVENT_UI as T } from '@/lib/terms'
import { addDaysIso, isoWeekday, WEEKDAYS_SHORT, wallToUtc } from '@/lib/time'
import { useTimeZone } from '@/lib/useTimeZone'
import { cn } from '@/lib/utils'

import { useCreateEvent } from './useCalendar'

const NONE = 'none'

export type EventDraft = { date: string; start?: string; end?: string }

function plusHour(t: string): string {
  const [h, m] = t.split(':').map(Number)
  return `${String(Math.min(h + 1, 23)).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** Новое жёсткое событие: разовое или с повтором по дням (правило без периода). */
export function EventDialog({
  open,
  onOpenChange,
  draft,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  draft?: EventDraft
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{T.newTitle}</DialogTitle>
        </DialogHeader>
        {open && <EventForm draft={draft} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function EventForm({ draft, onDone }: { draft?: EventDraft; onDone: () => void }) {
  const tz = useTimeZone()
  const createEvent = useCreateEvent()
  const createRule = useCreateScheduleRule()
  const { data: types = [] } = useEventTypes()
  const { data: areas } = useAreas()
  const [typeId, setTypeId] = useState<string>(NONE)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState(draft?.date ?? '')
  const [start, setStart] = useState(draft?.start ?? '19:00')
  const [end, setEnd] = useState(draft?.end ?? plusHour(draft?.start ?? '19:00'))
  const [repeat, setRepeat] = useState<number[]>([])
  const [until, setUntil] = useState('')
  const [areaId, setAreaId] = useState<string | null>(null)
  const [location, setLocation] = useState('')
  const [color, setColor] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [fields, setFields] = useState<FieldValues>({})
  const [error, setError] = useState<string | null>(null)
  const type = types.find((t) => t.id === typeId)
  const saving = createEvent.isPending || createRule.isPending

  const submit = async () => {
    setError(null)
    if (!title.trim() && !type) return setError(T.titleRequired)
    if (!date) return setError(T.dateRequired)
    if (start === end) return setError(T.sameTime)
    if (!repeat.length && end < start) return setError(T.endBeforeStart)
    try {
      if (repeat.length) {
        if (!type) return setError(T.typeForRepeat)
        await createRule.mutateAsync({
          event_type_id: type.id,
          area_id: areaId,
          title: title.trim() || null,
          pattern: { kind: 'weekly', weekdays: repeat, cycle_weeks: null },
          start_time: start,
          end_time: end,
          valid_from: date,
          valid_to: until || null,
          location: location.trim() || null,
          color,
          fields: compactValues(fields),
          note,
        })
      } else {
        await createEvent.mutateAsync({
          event_type_id: type?.id ?? null,
          area_id: areaId,
          title: title.trim() || type!.name,
          start: wallToUtc(date, start, tz),
          end: wallToUtc(end > start ? date : addDaysIso(date, 1), end, tz),
          location: location.trim() || null,
          color,
          note,
          fields: compactValues(fields),
        })
      }
      onDone()
    } catch {
      // тост уже показан
    }
  }

  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="ev-type">{T.type}</FieldLabel>
          <Select value={typeId} onValueChange={setTypeId}>
            <SelectTrigger id="ev-type" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{T.noType}</SelectItem>
              {types.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  <span className={cn('size-2.5 rounded-full', paletteColor(t.color).bg)} />
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="ev-title">{T.title}</FieldLabel>
          <Input id="ev-title" autoFocus placeholder={type?.name ?? T.titlePlaceholder} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_auto_auto]">
          <Field className="col-span-2 sm:col-span-1">
            <FieldLabel htmlFor="ev-date">{repeat.length ? T.from : T.when}</FieldLabel>
            <Input id="ev-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Input type="time" step={300} aria-label={T.start} className="sm:w-24" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input type="time" step={300} aria-label={T.end} className="sm:w-24" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <Field>
          <FieldLabel>{T.repeat}</FieldLabel>
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            className="w-full"
            value={repeat.map(String)}
            onValueChange={(v) => setRepeat(v.map(Number).sort((a, b) => a - b))}
          >
            {WEEKDAYS_SHORT.map((d, i) => (
              <ToggleGroupItem key={d} value={String(i + 1)} className="flex-1">
                {d}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <FieldDescription>
            {repeat.length ? T.repeatOn : T.noRepeat(date ? WEEKDAYS_SHORT[isoWeekday(date) - 1] : null)}
          </FieldDescription>
        </Field>
        {repeat.length > 0 && (
          <Field>
            <FieldLabel htmlFor="ev-until">{T.until}</FieldLabel>
            <Input id="ev-until" type="date" min={date} value={until} onChange={(e) => setUntil(e.target.value)} />
          </Field>
        )}
        <Field>
          <FieldLabel htmlFor="ev-area">{T.area}</FieldLabel>
          <AreaSelect id="ev-area" value={areaId} onChange={setAreaId} />
        </Field>
        <Field>
          <FieldLabel htmlFor="ev-location">{T.where}</FieldLabel>
          <Input id="ev-location" value={location} onChange={(e) => setLocation(e.target.value)} />
        </Field>
        {type && type.fields.length > 0 && (
          <FieldValuesForm defs={type.fields} value={fields} onChange={setFields} areas={areas} idPrefix="ev-field" />
        )}
        <Field>
          <FieldLabel>{T.color}</FieldLabel>
          <ColorPicker value={color} onChange={setColor} />
        </Field>
        <Field>
          <FieldLabel htmlFor="ev-note">{T.note}</FieldLabel>
          <Textarea id="ev-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {error && <FieldError>{error}</FieldError>}
      </FieldGroup>
      <DialogFooter>
        <Button type="submit" disabled={saving} className="ml-auto">
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
