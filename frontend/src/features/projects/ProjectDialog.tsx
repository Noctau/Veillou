import { useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { CategorySelect } from '@/features/catalog/CatalogSelect'

import { useCreateProject } from './useProjects'

type Props = { open: boolean; onOpenChange: (open: boolean) => void }

export function ProjectDialog({ open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый проект</DialogTitle>
        </DialogHeader>
        {open && <ProjectForm onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ProjectForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate()
  const create = useCreateProject()
  const [title, setTitle] = useState('')
  const [deadline, setDeadline] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [workDefault, setWorkDefault] = useState(false)

  const submit = () =>
    create.mutate(
      {
        title: title.trim(),
        deadline: deadline || null,
        category_id: categoryId,
        description,
        contacts: [],
        links: [],
        is_work_default: workDefault,
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
        if (title.trim()) submit()
      }}
    >
      <Field>
        <FieldLabel htmlFor="pr-title">Название</FieldLabel>
        <Input id="pr-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ВКР, поступление в магистратуру…" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field>
          <FieldLabel htmlFor="pr-deadline">Итоговый срок</FieldLabel>
          <Input id="pr-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="pr-category">Категория</FieldLabel>
          <CategorySelect id="pr-category" value={categoryId} onChange={setCategoryId} emptyLabel="Учёба" />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor="pr-desc">Описание</FieldLabel>
        <Textarea id="pr-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={workDefault} onCheckedChange={(v) => setWorkDefault(v === true)} />
        Сюда по умолчанию идут задания с работы
      </label>
      <DialogFooter>
        <Button type="submit" disabled={!title.trim() || create.isPending}>
          Создать
        </Button>
      </DialogFooter>
    </form>
  )
}
