import { PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

import { type ProjectDetail, useUpdateProject } from './useProjects'

type Contact = ProjectDetail['contacts'][number]

/** Контакты проекта (научный руководитель, консультант). Сохраняются кнопкой. */
export function ContactsEditor({ project }: { project: ProjectDetail }) {
  const update = useUpdateProject()
  const [contacts, setContacts] = useState<Contact[]>(project.contacts)
  const dirty = JSON.stringify(contacts) !== JSON.stringify(project.contacts)
  const valid = contacts.every((c) => c.name.trim())
  const patch = (i: number, c: Partial<Contact>) =>
    setContacts((old) => old.map((x, j) => (i === j ? { ...x, ...c } : x)))

  return (
    <div className="flex flex-col gap-3">
      {contacts.map((c, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <Input placeholder="Фамилия И. О." aria-label="Имя" value={c.name} onChange={(e) => patch(i, { name: e.target.value })} />
            <Button type="button" variant="ghost" size="icon" aria-label="Убрать" onClick={() => setContacts((old) => old.filter((_, j) => j !== i))}>
              <XIcon />
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="научный руководитель" aria-label="Роль" value={c.role ?? ''} onChange={(e) => patch(i, { role: e.target.value })} />
            <Input placeholder="почта, телефон" aria-label="Контакт" value={c.contact ?? ''} onChange={(e) => patch(i, { contact: e.target.value })} />
          </div>
        </div>
      ))}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setContacts((old) => [...old, { name: '', role: old.length ? '' : 'научный руководитель', contact: '' }])}
        >
          <PlusIcon /> Контакт
        </Button>
        {dirty && (
          <Button type="button" size="sm" disabled={!valid || update.isPending} onClick={() => update.mutate({ id: project.id, body: { contacts } })}>
            Сохранить
          </Button>
        )}
      </div>
    </div>
  )
}
