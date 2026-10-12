import { PlusIcon, RotateCcwIcon, SunriseIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useSettings, useUpdateSettings } from '@/features/settings/useSettings'
import { ACTION_TYPES_UI as T } from '@/lib/terms'

import { ActionTypeSelect, CategorySelect } from './CatalogSelect'
import { CategoryIcon } from './CategoryIcon'
import {
  type ActionType,
  byId,
  type TimeWindow,
  useActionTypes,
  useCategories,
  useCreateActionType,
  useDeleteActionType,
  useResetActionType,
  useUpdateActionType,
} from './useCatalog'
import { describeWindows, windowsValid } from './windows'
import { parseSynonyms } from './synonyms'
import { WindowsEditor } from './WindowsEditor'

const NEW_WINDOWS: TimeWindow[] = [{ weekdays: [1, 2, 3, 4, 5], start: '09:00', end: '19:00' }]

type Editing = { actionType?: ActionType } | null

export function ActionTypesSection() {
  const { data: types, isPending } = useActionTypes()
  const { data: categories } = useCategories()
  const cats = byId(categories)
  const [editing, setEditing] = useState<Editing>(null)

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
        <DefaultActionType />
        {isPending && <Skeleton className="h-40" />}
        <ul className="flex flex-col">
          {types?.map((t) => {
            const cat = t.default_category_id ? cats.get(t.default_category_id) : undefined
            return (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => setEditing({ actionType: t })}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      {t.name}
                      {t.prefer_morning && <SunriseIcon className="size-3.5 text-muted-foreground" aria-label={T.morning} />}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{describeWindows(t.windows)}</div>
                  </div>
                  {cat && <CategoryIcon name={cat.icon} className="size-4 text-muted-foreground" aria-label={cat.name} />}
                </button>
              </li>
            )
          })}
        </ul>
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing?.actionType?.name ?? T.newTitle}</DialogTitle>
          </DialogHeader>
          {editing && (
            <ActionTypeForm key={editing.actionType?.id ?? 'new'} actionType={editing.actionType} onDone={() => setEditing(null)} />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/** Тип по умолчанию: для задач и дел без своего типа (окна, лимиты, утро). */
function DefaultActionType() {
  const { data: settings } = useSettings()
  const update = useUpdateSettings()
  if (!settings) return null
  return (
    <Field>
      <FieldLabel htmlFor="at-default">{T.default}</FieldLabel>
      <ActionTypeSelect
        id="at-default"
        value={settings.default_action_type_id}
        onChange={(default_action_type_id) => update.mutate({ default_action_type_id })}
        emptyLabel={T.noDefault}
      />
      <FieldDescription>{T.defaultHint}</FieldDescription>
    </Field>
  )
}

function ActionTypeForm({ actionType, onDone }: { actionType?: ActionType; onDone: () => void }) {
  const create = useCreateActionType()
  const update = useUpdateActionType()
  const reset = useResetActionType()
  const remove = useDeleteActionType()
  const [name, setName] = useState(actionType?.name ?? '')
  const [windows, setWindows] = useState<TimeWindow[]>(actionType?.windows ?? NEW_WINDOWS)
  const [categoryId, setCategoryId] = useState(actionType?.default_category_id ?? null)
  const [morning, setMorning] = useState(actionType?.prefer_morning ?? false)
  const [synonyms, setSynonyms] = useState(actionType?.synonyms.join(', ') ?? '')
  const valid = name.trim() !== '' && windows.length > 0 && windowsValid(windows)
  const saving = create.isPending || update.isPending

  const save = () => {
    const body = {
      name: name.trim(),
      windows,
      default_category_id: categoryId,
      prefer_morning: morning,
      synonyms: parseSynonyms(synonyms),
    }
    if (actionType) update.mutate({ id: actionType.id, body }, { onSuccess: onDone })
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
        <FieldLabel htmlFor="at-name">{T.name}</FieldLabel>
        <Input id="at-name" autoFocus={!actionType} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>{T.windows}</FieldLabel>
        <WindowsEditor value={windows} onChange={setWindows} template={windows.at(-1)} />
        {windows.length === 0 && <FieldDescription className="text-destructive">{T.windowsRequired}</FieldDescription>}
      </Field>
      <Field>
        <FieldLabel htmlFor="at-category">{T.category}</FieldLabel>
        <CategorySelect id="at-category" value={categoryId} onChange={setCategoryId} emptyLabel={T.noCategory} />
      </Field>
      <Field>
        <FieldLabel htmlFor="at-synonyms">{T.synonyms}</FieldLabel>
        <Input id="at-synonyms" value={synonyms} onChange={(e) => setSynonyms(e.target.value)} />
        <FieldDescription>{T.synonymsHint}</FieldDescription>
      </Field>
      <Field orientation="horizontal">
        <Switch id="at-morning" checked={morning} onCheckedChange={setMorning} />
        <div className="flex flex-col">
          <FieldLabel htmlFor="at-morning">{T.morning}</FieldLabel>
          <FieldDescription>{T.morningHint}</FieldDescription>
        </div>
      </Field>
      <DialogFooter className="flex-row items-center">
        {actionType && (
          <ConfirmButton
            title={T.deleteTitle(actionType.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(actionType.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label={T.deleteLabel} className="text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        {actionType?.key && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={reset.isPending}
            onClick={() => reset.mutate(actionType.id, { onSuccess: onDone })}
          >
            <RotateCcwIcon /> {T.reset}
          </Button>
        )}
        <Button type="submit" className="ml-auto" disabled={!valid || saving}>
          {saving ? T.saving : T.save}
        </Button>
      </DialogFooter>
    </form>
  )
}
