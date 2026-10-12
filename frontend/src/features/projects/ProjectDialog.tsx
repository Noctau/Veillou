import { useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { AreaSelect } from '@/features/areas/AreaSelect'
import { CategorySelect } from '@/features/catalog/CatalogSelect'
import { AREAS_UI } from '@/lib/terms'

import { useCreateProject } from './useProjects'

type Props = { open: boolean; onOpenChange: (open: boolean) => void; areaId?: string }

export function ProjectDialog({ open, onOpenChange, areaId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый проект</DialogTitle>
        </DialogHeader>
        {open && <ProjectForm areaId={areaId} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ProjectForm({ areaId: initialArea, onDone }: { areaId?: string; onDone: () => void }) {
  const navigate = useNavigate()
  const create = useCreateProject()
  const [title, setTitle] = useState('')
  const [deadline, setDeadline] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [areaId, setAreaId] = useState<string | null>(initialArea ?? null)
  const [description, setDescription] = useState('')
  const [hours, setHours] = useState('')
  const norm = hours ? Math.round(Number(hours) * 60) : null
  const normValid = norm === null || (norm >= 0 && norm <= 60 * 60)

  const submit = () =>
    create.mutate(
      {
        title: title.trim(),
        deadline: deadline || null,
        category_id: categoryId,
        area_id: areaId,
        description,
        contacts: [],
        links: [],
        weekly_norm_min: norm || null,
      },
      {
        onSuccess: (project) => {
          onDone()
          navigate(`/projects/${project.id}`)
        },
      },
    )

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (title.trim() && normValid) submit()
      }}
    >
      <Field>
        <FieldLabel htmlFor="pr-title">Название</FieldLabel>
        <Input id="pr-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Диплом, ремонт, запуск сайта…" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="pr-deadline">Итоговый срок</FieldLabel>
          <Input id="pr-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="pr-category">Категория</FieldLabel>
          <CategorySelect id="pr-category" value={categoryId} onChange={setCategoryId} emptyLabel="По умолчанию" />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor="pr-area">{AREAS_UI.area}</FieldLabel>
        <AreaSelect id="pr-area" value={areaId} onChange={setAreaId} />
      </Field>
      <Field>
        <FieldLabel htmlFor="pr-norm">Часов в неделю</FieldLabel>
        <Input
          id="pr-norm"
          type="number"
          inputMode="decimal"
          min={0}
          max={60}
          step={0.5}
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          placeholder="Необязательно — план зарезервирует это время"
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="pr-desc">Описание</FieldLabel>
        <Textarea id="pr-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={!title.trim() || !normValid || create.isPending}>
          Создать
        </Button>
      </DialogFooter>
    </form>
  )
}
