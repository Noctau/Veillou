import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useEventTypes } from '@/features/schedule/useSchedule'
import { BUDGETS_UI as T } from '@/lib/terms'

import {
  byId,
  type LoadBudget,
  useActionTypes,
  useBudgets,
  useCreateBudget,
  useDeleteBudget,
  useUpdateBudget,
} from './useCatalog'

type Editing = { budget?: LoadBudget } | null

/** Лимиты нагрузки (M15.3): «не больше N часов в день» на группу типов действий и занятости. */
export function BudgetsSection() {
  const { data: budgets, isPending } = useBudgets()
  const types = byId(useActionTypes().data)
  const eventTypes = byId(useEventTypes().data)
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
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-16" />}
        {budgets && budgets.length === 0 && <p className="text-sm text-muted-foreground">{T.empty}</p>}
        <ul className="flex flex-col">
          {budgets?.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                onClick={() => setEditing({ budget: b })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{b.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[
                      ...b.action_type_ids.map((id) => types.get(id)?.name),
                      ...b.event_type_ids.map((id) => eventTypes.get(id)?.name),
                    ]
                      .filter(Boolean)
                      .join(', ')}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {T.perDay(b.minutes_per_day / 60)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing?.budget?.name ?? T.newTitle}</DialogTitle>
          </DialogHeader>
          {editing && <BudgetForm key={editing.budget?.id ?? 'new'} budget={editing.budget} onDone={() => setEditing(null)} />}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function BudgetForm({ budget, onDone }: { budget?: LoadBudget; onDone: () => void }) {
  const { data: types } = useActionTypes()
  const { data: eventTypes } = useEventTypes()
  const create = useCreateBudget()
  const update = useUpdateBudget()
  const remove = useDeleteBudget()
  const [name, setName] = useState(budget?.name ?? '')
  const [hours, setHours] = useState(budget ? budget.minutes_per_day / 60 : 4)
  const [members, setMembers] = useState<string[]>(budget?.action_type_ids ?? [])
  const [eventMembers, setEventMembers] = useState<string[]>(budget?.event_type_ids ?? [])
  const minutes = Math.round(hours * 60)
  const valid = name.trim() !== '' && minutes >= 15 && minutes <= 1440
  const saving = create.isPending || update.isPending

  const save = () => {
    const body = {
      name: name.trim(),
      minutes_per_day: minutes,
      action_type_ids: members,
      event_type_ids: eventMembers,
    }
    if (budget) update.mutate({ id: budget.id, body }, { onSuccess: onDone })
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
        <FieldLabel htmlFor="lb-name">{T.name}</FieldLabel>
        <Input id="lb-name" autoFocus={!budget} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="lb-hours">{T.hours}</FieldLabel>
        <Input
          id="lb-hours"
          type="number"
          inputMode="decimal"
          min={0.25}
          max={24}
          step={0.5}
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="w-28"
        />
      </Field>
      <Field>
        <FieldLabel>{T.members}</FieldLabel>
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          className="flex-wrap justify-start"
          value={members}
          onValueChange={setMembers}
        >
          {types?.map((t) => (
            <ToggleGroupItem key={t.id} value={t.id} className="rounded-full! border px-3">
              {t.name}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <FieldDescription>{T.membersHint}</FieldDescription>
      </Field>
      {!!eventTypes?.length && (
        <Field>
          <FieldLabel>{T.eventMembers}</FieldLabel>
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            className="flex-wrap justify-start"
            value={eventMembers}
            onValueChange={setEventMembers}
          >
            {eventTypes.map((t) => (
              <ToggleGroupItem key={t.id} value={t.id} className="rounded-full! border px-3">
                {t.name}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <FieldDescription>{T.eventMembersHint}</FieldDescription>
        </Field>
      )}
      <DialogFooter className="flex-row items-center">
        {budget && (
          <ConfirmButton
            title={T.deleteTitle(budget.name)}
            description={T.deleteDescription}
            onConfirm={() => remove.mutate(budget.id, { onSuccess: onDone })}
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
