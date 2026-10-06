import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ColorPicker } from '@/components/common/ColorPicker'
import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { paletteColor } from '@/lib/colors'
import { cn } from '@/lib/utils'

import { CategoryIcon } from './CategoryIcon'
import { CATEGORY_ICONS } from './icons'
import {
  type Category,
  type CategoryIconName,
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
} from './useCatalog'

type Editing = { category?: Category } | null

export function CategoriesSection() {
  const { data: categories, isPending } = useCategories()
  const [editing, setEditing] = useState<Editing>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Категории</CardTitle>
        <CardDescription>Что это за дело: цвет и иконка в календаре, фильтр в списках.</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={() => setEditing({})}>
            <PlusIcon /> Категория
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="pt-2">
        {isPending && <Skeleton className="h-24" />}
        <ul className="flex flex-wrap gap-2">
          {categories?.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => setEditing({ category: c })}
                className="flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm hover:bg-muted"
              >
                <span className={cn('flex size-5 items-center justify-center rounded-full text-white', paletteColor(c.color).bg)}>
                  <CategoryIcon name={c.icon} className="size-3" />
                </span>
                {c.name}
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing?.category ? 'Категория' : 'Новая категория'}</DialogTitle>
          </DialogHeader>
          {editing && <CategoryForm category={editing.category} onDone={() => setEditing(null)} />}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function CategoryForm({ category, onDone }: { category?: Category; onDone: () => void }) {
  const create = useCreateCategory()
  const update = useUpdateCategory()
  const remove = useDeleteCategory()
  const [name, setName] = useState(category?.name ?? '')
  const [color, setColor] = useState(category?.color ?? '#64748b')
  const [icon, setIcon] = useState<CategoryIconName>(category?.icon ?? 'tag')
  const saving = create.isPending || update.isPending

  const save = () => {
    const body = { name: name.trim(), color, icon }
    if (category) update.mutate({ id: category.id, body }, { onSuccess: onDone })
    else create.mutate(body, { onSuccess: onDone })
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="cat-name">Название</FieldLabel>
        <Input id="cat-name" autoFocus={!category} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Цвет</FieldLabel>
        <ColorPicker value={color} onChange={setColor} />
      </Field>
      <Field>
        <FieldLabel>Иконка</FieldLabel>
        <div role="radiogroup" className="flex flex-wrap gap-2">
          {(Object.keys(CATEGORY_ICONS) as CategoryIconName[]).map((key) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={icon === key}
              aria-label={key}
              onClick={() => setIcon(key)}
              className={cn(
                'flex size-9 items-center justify-center rounded-lg border',
                icon === key && 'border-foreground bg-muted',
              )}
            >
              <CategoryIcon name={key} className="size-4" />
            </button>
          ))}
        </div>
      </Field>
      <DialogFooter className="flex-row items-center">
        {category && !category.key && (
          <ConfirmButton
            title={`Удалить «${category.name}»?`}
            description="Дела с этой категорией останутся, но без категории."
            onConfirm={() => remove.mutate(category.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить категорию" className="mr-auto text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" disabled={!name.trim() || saving} className="ml-auto">
          {saving ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </DialogFooter>
    </form>
  )
}
