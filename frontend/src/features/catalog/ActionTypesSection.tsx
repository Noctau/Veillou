import { RotateCcwIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

import { CategoryIcon } from './CategoryIcon'
import {
  type ActionType,
  byId,
  type TimeWindow,
  useActionTypes,
  useCategories,
  useResetActionType,
  useUpdateActionType,
} from './useCatalog'
import { describeWindows, windowsValid } from './windows'
import { WindowsEditor } from './WindowsEditor'

const NO_CATEGORY = 'none'

export function ActionTypesSection() {
  const { data: types, isPending } = useActionTypes()
  const { data: categories } = useCategories()
  const cats = byId(categories)
  const [editing, setEditing] = useState<ActionType | null>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Типы действий</CardTitle>
        <CardDescription>
          Когда уместно делать дела каждого типа. Окно типа важнее рабочих часов: учёбу можно ночью, а писать
          научруку — только днём.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-40" />}
        <ul className="flex flex-col">
          {types?.map((t) => {
            const cat = t.default_category_id ? cats.get(t.default_category_id) : undefined
            return (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => setEditing(t)}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{t.name}</div>
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
            <DialogTitle>{editing?.name}</DialogTitle>
          </DialogHeader>
          {editing && <ActionTypeForm key={editing.id} actionType={editing} onDone={() => setEditing(null)} />}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function ActionTypeForm({ actionType, onDone }: { actionType: ActionType; onDone: () => void }) {
  const { data: categories } = useCategories()
  const update = useUpdateActionType()
  const reset = useResetActionType()
  const [name, setName] = useState(actionType.name)
  const [windows, setWindows] = useState<TimeWindow[]>(actionType.windows)
  const [categoryId, setCategoryId] = useState(actionType.default_category_id ?? NO_CATEGORY)
  const valid = name.trim() !== '' && windows.length > 0 && windowsValid(windows)

  const save = () =>
    update.mutate(
      {
        id: actionType.id,
        body: {
          name: name.trim(),
          windows,
          default_category_id: categoryId === NO_CATEGORY ? null : categoryId,
        },
      },
      { onSuccess: onDone },
    )

  return (
    <div className="flex flex-col gap-5">
      <Field>
        <FieldLabel htmlFor="at-name">Название</FieldLabel>
        <Input id="at-name" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Когда можно</FieldLabel>
        <WindowsEditor value={windows} onChange={setWindows} template={windows.at(-1)} />
        {windows.length === 0 && <FieldDescription className="text-destructive">Нужно хотя бы одно окно.</FieldDescription>}
      </Field>
      <Field>
        <FieldLabel htmlFor="at-category">Категория по умолчанию</FieldLabel>
        <Select value={categoryId} onValueChange={setCategoryId}>
          <SelectTrigger id="at-category" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_CATEGORY}>Без категории</SelectItem>
            {categories?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <DialogFooter className="flex-row items-center">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mr-auto"
          disabled={reset.isPending}
          onClick={() => reset.mutate(actionType.id, { onSuccess: onDone })}
        >
          <RotateCcwIcon /> По умолчанию
        </Button>
        <Button type="button" disabled={!valid || update.isPending} onClick={save}>
          {update.isPending ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </DialogFooter>
    </div>
  )
}
