import { ArrowLeftIcon, CalendarClockIcon, ExternalLinkIcon, MoreVerticalIcon, Trash2Icon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { AttachmentList } from '@/features/attachments/AttachmentList'
import { useAttachments } from '@/features/attachments/useAttachments'
import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { useSubjects } from '@/features/subjects/useSubjects'
import { errorMessage } from '@/lib/errors'

import { isPageImage, NOTE_KIND, NOTE_KINDS, pairLabel } from './labels'
import { NotePages } from './NotePages'
import { NoteTextEditor } from './NoteTextEditor'
import { type Note, type NoteKind, type NoteUpdate, useDeleteNote, useNote, useUpdateNote } from './useNotes'

const NONE = 'none'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="pt-2">{children}</CardContent>
    </Card>
  )
}

function TitleEditor({ note, onSave }: { note: Note; onSave: (title: string) => void }) {
  const [value, setValue] = useState(note.title)
  const commit = () => {
    const title = value.trim()
    if (title && title !== note.title) onSave(title)
    else setValue(note.title)
  }
  return (
    <Textarea
      value={value}
      rows={1}
      aria-label="Название конспекта"
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        }
      }}
      className="min-h-0 resize-none border-none bg-transparent! px-0 text-2xl font-semibold shadow-none focus-visible:ring-0 md:text-2xl"
    />
  )
}

/** Ссылка на Диск / сайт. Без схемы допишем https://. */
function LinkEditor({ note, onSave }: { note: Note; onSave: (url: string | null) => void }) {
  const [value, setValue] = useState(note.url ?? '')
  const [invalid, setInvalid] = useState(false)
  const commit = () => {
    const raw = value.trim()
    if (!raw) {
      setInvalid(false)
      if (note.url) onSave(null)
      return
    }
    const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`
    try {
      const url = new URL(withScheme)
      if (!/^https?:$/.test(url.protocol)) throw new Error()
      setInvalid(false)
      setValue(url.href)
      if (url.href !== note.url) onSave(url.href)
    } catch {
      setInvalid(true)
    }
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2">
        <Input
          type="url"
          inputMode="url"
          value={value}
          placeholder="https://disk.yandex.ru/…"
          aria-label="Ссылка"
          aria-invalid={invalid}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        />
        {note.url && (
          <Button asChild variant="outline">
            <a href={note.url} target="_blank" rel="noreferrer">
              <ExternalLinkIcon /> Открыть
            </a>
          </Button>
        )}
      </div>
      {invalid && <p className="text-xs text-destructive">Это не похоже на ссылку</p>}
    </div>
  )
}

function Meta({ note, patch }: { note: Note; patch: (body: NoteUpdate) => void }) {
  const tz = useTimeZone()
  const { data: subjects } = useSubjects()
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <Select value={note.subject_id ?? NONE} onValueChange={(v) => patch({ subject_id: v === NONE ? null : v })}>
        <SelectTrigger size="sm" aria-label="Предмет" className="max-w-56">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>Без предмета</SelectItem>
          {subjects?.map((s) => (
            <SelectItem key={s.id} value={s.id}>
              {s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        type="date"
        aria-label="Дата пары"
        value={note.class_date ?? ''}
        onChange={(e) => patch({ class_date: e.target.value || null })}
        className="h-8 w-40"
      />
      {note.event && (
        <span className="flex items-center gap-1">
          <CalendarClockIcon className="size-4" />
          {pairLabel(note.event, tz)}
        </span>
      )}
    </div>
  )
}

export function NoteView({ noteId }: { noteId: string }) {
  const navigate = useNavigate()
  const { data: note, isPending, isError, error } = useNote(noteId)
  const { data: attachments = [] } = useAttachments('note', noteId)
  const update = useUpdateNote()
  const remove = useDeleteNote()
  const [shown, setShown] = useState<Set<NoteKind>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (isError) return <p className="text-sm text-destructive">{errorMessage(error)}</p>

  const patch = (body: NoteUpdate) => update.mutate({ id: note.id, body })
  const pages = attachments.filter(isPageImage)
  const files = attachments.filter((a) => !isPageImage(a))
  const hasContent: Record<NoteKind, boolean> = {
    text: !!note.body_md.trim(),
    photo: pages.length > 0,
    file: files.length > 0,
    link: !!note.url,
  }
  // Основной вид — первым; остальные — если в них что-то есть или их добавили
  const sections = [note.kind, ...NOTE_KINDS.filter((k) => k !== note.kind && (hasContent[k] || shown.has(k)))]
  const addable = NOTE_KINDS.filter((k) => !sections.includes(k))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-1">
        <Button variant="ghost" size="icon" aria-label="Назад" className="-ml-2 shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeftIcon />
        </Button>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <TitleEditor key={note.title} note={note} onSave={(title) => patch({ title })} />
          <Meta note={note} patch={patch} />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Ещё">
              <MoreVerticalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {note.subject_id && (
              <DropdownMenuItem asChild>
                <Link to={`/subjects/${note.subject_id}?tab=notes`}>Все конспекты предмета</Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2Icon /> Удалить конспект
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {sections.map((kind) => (
        <Section key={kind} title={kind === 'file' ? 'Файлы' : NOTE_KIND[kind].label}>
          {kind === 'text' && (
            <NoteTextEditor value={note.body_md} onSave={(body_md) => patch({ body_md })} autoFocus={shown.has('text')} />
          )}
          {kind === 'photo' && <NotePages noteId={note.id} attachments={attachments} />}
          {kind === 'file' && (
            <AttachmentList
              ownerType="note"
              ownerId={note.id}
              filter={(a) => !isPageImage(a)}
              pdfPreview
              uploadLabel="PDF или другой файл"
            />
          )}
          {kind === 'link' && <LinkEditor note={note} onSave={(url) => patch({ url })} />}
        </Section>
      ))}

      {addable.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Добавить:</span>
          {addable.map((kind) => {
            const { label, icon: Icon } = NOTE_KIND[kind]
            return (
              <Button key={kind} variant="outline" size="sm" onClick={() => setShown((old) => new Set(old).add(kind))}>
                <Icon /> {label}
              </Button>
            )
          })}
        </div>
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить «{note.title}»?</AlertDialogTitle>
            <AlertDialogDescription>Текст, страницы и файлы конспекта удалятся.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => remove.mutate(note.id, { onSuccess: () => navigate(-1) })}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
