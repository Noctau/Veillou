import { ArchiveIcon, CheckIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { ActionTypeSelect, CategorySelect } from '@/features/catalog/CatalogSelect'

import { CONDITION_LABEL, CONDITIONS, ESTIMATES } from './labels'
import { type BacklogCondition, type BacklogItem, useDeleteBacklog, useUpdateBacklog } from './useBacklog'

type Props = { item: BacklogItem | null; onOpenChange: (open: boolean) => void }

export function BacklogItemDialog({ item, onOpenChange }: Props) {
  return (
    <Dialog open={!!item} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Дело</DialogTitle>
        </DialogHeader>
        {item && <BacklogForm key={item.id} item={item} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function BacklogForm({ item, onDone }: { item: BacklogItem; onDone: () => void }) {
  const update = useUpdateBacklog()
  const remove = useDeleteBacklog()
  const [title, setTitle] = useState(item.title)
  const [note, setNote] = useState(item.note)
  const [categoryId, setCategoryId] = useState(item.category_id)
  const [actionTypeId, setActionTypeId] = useState(item.action_type_id)
  const [estimate, setEstimate] = useState(item.estimate_min)
  const [desiredBy, setDesiredBy] = useState(item.desired_by ?? '')
  const [conditions, setConditions] = useState<BacklogCondition[]>(item.conditions)
  const pending = item.id.startsWith('tmp-')

  const save = () =>
    update.mutate(
      {
        id: item.id,
        body: {
          title: title.trim(),
          note,
          category_id: categoryId,
          action_type_id: actionTypeId,
          estimate_min: estimate,
          desired_by: desiredBy || null,
          conditions,
        },
      },
      { onSuccess: onDone },
    )
  const setStatus = (status: BacklogItem['status']) => {
    update.mutate({ id: item.id, body: { status } })
    onDone()
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (title.trim()) save()
      }}
    >
      <Field>
        <FieldLabel htmlFor="bl-title">Что сделать</FieldLabel>
        <Input id="bl-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Примерно займёт</FieldLabel>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="w-full"
          value={estimate ? String(estimate) : ''}
          onValueChange={(v) => setEstimate(v ? Number(v) : null)}
        >
          {ESTIMATES.map((e) => (
            <ToggleGroupItem key={e.value} value={String(e.value)} className="flex-1">
              {e.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <Field>
        <FieldLabel htmlFor="bl-desired">Хорошо бы до</FieldLabel>
        <Input id="bl-desired" type="date" value={desiredBy} onChange={(e) => setDesiredBy(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Условия</FieldLabel>
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          className="flex-wrap justify-start"
          value={conditions}
          onValueChange={(v) => setConditions(v as BacklogCondition[])}
        >
          {CONDITIONS.map((c) => (
            <ToggleGroupItem key={c} value={c} className="rounded-full! border px-3">
              {CONDITION_LABEL[c]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="bl-category">Категория</FieldLabel>
          <CategorySelect id="bl-category" value={categoryId} onChange={setCategoryId} />
        </Field>
        <Field>
          <FieldLabel htmlFor="bl-type">Тип действия</FieldLabel>
          <ActionTypeSelect id="bl-type" value={actionTypeId} onChange={setActionTypeId} />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor="bl-note">Заметка</FieldLabel>
        <Textarea id="bl-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>

      <div className="flex flex-wrap gap-2">
        {item.status === 'active' ? (
          <>
            <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => setStatus('done')}>
              <CheckIcon /> Сделано
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => setStatus('archived')}>
              <ArchiveIcon /> Неактуально
            </Button>
          </>
        ) : (
          <Button type="button" variant="outline" size="sm" onClick={() => setStatus('active')}>
            <RotateCcwIcon /> Вернуть в ящик
          </Button>
        )}
      </div>

      <DialogFooter className="flex-row items-center">
        <ConfirmButton
          title={`Удалить «${item.title}»?`}
          onConfirm={() => remove.mutate(item.id, { onSuccess: onDone })}
        >
          <Button type="button" variant="ghost" size="icon" aria-label="Удалить" disabled={pending} className="mr-auto text-destructive">
            <Trash2Icon />
          </Button>
        </ConfirmButton>
        <Button type="submit" disabled={!title.trim() || update.isPending || pending}>
          Сохранить
        </Button>
      </DialogFooter>
    </form>
  )
}
