import { Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { AttachmentList } from '@/features/attachments/AttachmentList'
import { normalizeUrl } from '@/lib/url'

import {
  SOURCE_KIND_LABEL,
  type Source,
  type SourceKind,
  useCreateSource,
  useDeleteSource,
  useUpdateSource,
} from './useSources'

const KINDS = Object.keys(SOURCE_KIND_LABEL) as SourceKind[]

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  subjectId: string
  /** Нет — новый источник. */
  source?: Source
}

export function SourceDialog({ open, onOpenChange, subjectId, source }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{source ? 'Источник' : 'Новый источник'}</DialogTitle>
        </DialogHeader>
        {open && (
          <SourceForm key={source?.id ?? 'new'} subjectId={subjectId} source={source} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SourceForm({ subjectId, source, onDone }: { subjectId: string; source?: Source; onDone: () => void }) {
  const create = useCreateSource()
  const update = useUpdateSource(subjectId)
  const remove = useDeleteSource()
  const [title, setTitle] = useState(source?.title ?? '')
  const [author, setAuthor] = useState(source?.author ?? '')
  const [kind, setKind] = useState<SourceKind>(source?.kind ?? 'textbook')
  const [required, setRequired] = useState(source?.required ?? true)
  const [url, setUrl] = useState(source?.url ?? '')
  const [note, setNote] = useState(source?.note ?? '')
  const [urlError, setUrlError] = useState(false)

  const save = () => {
    const link = url.trim() ? normalizeUrl(url) : null
    if (url.trim() && !link) {
      setUrlError(true)
      return
    }
    const body = { title: title.trim(), author: author.trim(), kind, required, url: link, note }
    if (source) update.mutate({ id: source.id, body }, { onSuccess: onDone })
    else create.mutate({ ...body, subject_id: subjectId, status: 'to_read' }, { onSuccess: onDone })
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
        <FieldLabel htmlFor="src-title">Название</FieldLabel>
        <Input id="src-title" autoFocus={!source} value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel htmlFor="src-author">Автор</FieldLabel>
        <Input id="src-author" value={author} placeholder="Матвеев Л. Т." onChange={(e) => setAuthor(e.target.value)} />
      </Field>
      <Field>
        <FieldLabel>Тип</FieldLabel>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="w-full"
          value={kind}
          onValueChange={(v) => v && setKind(v as SourceKind)}
        >
          {KINDS.map((k) => (
            <ToggleGroupItem key={k} value={k} className="flex-1">
              {SOURCE_KIND_LABEL[k]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <Field orientation="horizontal">
        <Switch id="src-required" checked={required} onCheckedChange={setRequired} />
        <FieldLabel htmlFor="src-required">{required ? 'Обязательная литература' : 'Дополнительная литература'}</FieldLabel>
      </Field>
      <Field data-invalid={urlError}>
        <FieldLabel htmlFor="src-url">Ссылка</FieldLabel>
        <Input
          id="src-url"
          type="text"
          inputMode="url"
          autoComplete="url"
          value={url}
          placeholder="https://…"
          aria-invalid={urlError}
          onChange={(e) => {
            setUrl(e.target.value)
            setUrlError(false)
          }}
        />
        {urlError && <FieldError>Это не похоже на ссылку</FieldError>}
      </Field>
      <Field>
        <FieldLabel htmlFor="src-note">Заметка</FieldLabel>
        <Textarea id="src-note" rows={2} value={note} placeholder="какие главы нужны, где взять" onChange={(e) => setNote(e.target.value)} />
      </Field>
      {source && (
        <Field>
          <FieldLabel>Файл</FieldLabel>
          <AttachmentList ownerType="source" ownerId={source.id} uploadLabel="PDF, DJVU…" />
        </Field>
      )}

      <DialogFooter className="flex-row items-center">
        {source && (
          <ConfirmButton
            title={`Удалить «${source.title}»?`}
            onConfirm={() => remove.mutate(source.id, { onSuccess: onDone })}
          >
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить" className="mr-auto text-destructive">
              <Trash2Icon />
            </Button>
          </ConfirmButton>
        )}
        <Button type="submit" disabled={!title.trim() || create.isPending || update.isPending}>
          {source ? 'Сохранить' : 'Добавить'}
        </Button>
      </DialogFooter>
    </form>
  )
}
