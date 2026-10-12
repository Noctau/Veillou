import { ArchiveIcon, ArchiveRestoreIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { usePeriods } from '@/features/schedule/useSchedule'
import { PALETTE } from '@/lib/colors'
import { AREAS_UI as T } from '@/lib/terms'

import { compactValues } from './fields'
import { FieldValuesForm } from './FieldValuesForm'
import {
  type Area,
  type AreaType,
  type FieldValues,
  useAreas,
  useAreaTypes,
  useCreateArea,
  useDeleteArea,
  useUpdateArea,
} from './useAreas'

const NONE = 'none'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  area?: Area
  /** Тип новой сферы; не задан — выбирается в форме. */
  areaTypeId?: string
  periodId?: string
  /** Для новой сферы — следующий цвет палитры, чтобы сферы различались. */
  colorIndex?: number
  /** После удаления (со страницы сферы — уйти с неё). */
  onDeleted?: () => void
}

export function AreaDialog({ open, onOpenChange, area, areaTypeId, periodId, colorIndex, onDeleted }: Props) {
  const { data: types } = useAreaTypes()
  const typeId = area?.area_type_id ?? areaTypeId ?? types?.[0]?.id
  const areaType = types?.find((t) => t.id === typeId)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{area ? area.name : areaType ? T.newTitle(areaType.name) : T.area}</DialogTitle>
        </DialogHeader>
        {open && types && (
          <AreaForm
            key={area?.id ?? 'new'}
            area={area}
            types={types}
            initialTypeId={typeId}
            periodId={periodId}
            colorIndex={colorIndex}
            onDone={() => onOpenChange(false)}
            onDeleted={onDeleted}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function AreaForm({
  area,
  types,
  initialTypeId,
  periodId,
  colorIndex = 0,
  onDone,
  onDeleted,
}: {
  area?: Area
  types: AreaType[]
  initialTypeId?: string
  periodId?: string
  colorIndex?: number
  onDone: () => void
  onDeleted?: () => void
}) {
  const create = useCreateArea()
  const update = useUpdateArea()
  const remove = useDeleteArea()
  const { data: periods } = usePeriods()
  const { data: allAreas } = useAreas()
  const [typeId, setTypeId] = useState(initialTypeId ?? '')
  const areaType = types.find((t) => t.id === typeId)
  const [name, setName] = useState(area?.name ?? '')
  const [shortName, setShortName] = useState(area?.short_name ?? '')
  const [color, setColor] = useState(area?.color ?? areaType?.color ?? PALETTE[colorIndex % PALETTE.length].hex)
  const [period, setPeriod] = useState(area ? (area.period_id ?? NONE) : (periodId ?? NONE))
  const [synonyms, setSynonyms] = useState(area?.synonyms.join(', ') ?? '')
  const [notes, setNotes] = useState(area?.notes ?? '')
  const [fields, setFields] = useState<FieldValues>(area?.fields ?? {})
  const saving = create.isPending || update.isPending
  const valid = name.trim() !== '' && !!areaType
  const refAreas = (allAreas ?? []).filter((a) => a.id !== area?.id && !a.archived_at)

  const save = () => {
    if (!areaType) return
    const body = {
      name: name.trim(),
      short_name: shortName.trim() || null,
      color,
      period_id: period === NONE ? null : period,
      synonyms: synonyms
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      notes,
      fields: compactValues(fields),
    }
    if (area) update.mutate({ id: area.id, body }, { onSuccess: onDone })
    else create.mutate({ ...body, area_type_id: areaType.id }, { onSuccess: onDone })
  }

  return (
    <form
      noValidate
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save()
      }}
    >
      <FieldGroup>
        {!area && types.length > 1 && (
          <Field>
            <FieldLabel htmlFor="area-type">{T.type}</FieldLabel>
            <Select value={typeId} onValueChange={setTypeId}>
              <SelectTrigger id="area-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {types.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
        <Field>
          <FieldLabel htmlFor="area-name">{T.name}</FieldLabel>
          <Input id="area-name" autoFocus={!area} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field>
            <FieldLabel htmlFor="area-short">{T.shortName}</FieldLabel>
            <Input id="area-short" maxLength={50} value={shortName} onChange={(e) => setShortName(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="area-period">{T.period}</FieldLabel>
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger id="area-period" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{T.noPeriod}</SelectItem>
                {periods?.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field>
          <FieldLabel>{T.color}</FieldLabel>
          <ColorPicker value={color} onChange={setColor} />
        </Field>
        {areaType && (
          <FieldValuesForm defs={areaType.fields} value={fields} onChange={setFields} areas={refAreas} idPrefix="area-field" />
        )}
        <Field>
          <FieldLabel htmlFor="area-synonyms">{T.synonyms}</FieldLabel>
          <Input id="area-synonyms" value={synonyms} onChange={(e) => setSynonyms(e.target.value)} />
          <FieldDescription>{T.synonymsHint}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="area-notes">{T.notes}</FieldLabel>
          <Textarea id="area-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </FieldGroup>

      <DialogFooter className="flex-row items-center">
        {area && (
          <>
            <ConfirmButton
              title={T.deleteTitle(area.name)}
              description={T.deleteDescription}
              onConfirm={() =>
                remove.mutate(area.id, {
                  onSuccess: () => {
                    onDone()
                    onDeleted?.()
                  },
                })
              }
            >
              <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
                <Trash2Icon />
              </Button>
            </ConfirmButton>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => update.mutate({ id: area.id, body: { archived: !area.archived_at } }, { onSuccess: onDone })}
            >
              {area.archived_at ? <ArchiveRestoreIcon /> : <ArchiveIcon />}
              {area.archived_at ? T.unarchive : T.archive}
            </Button>
          </>
        )}
        <Button type="submit" disabled={!valid || saving} className="ml-auto">
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
