import {
  BookIcon,
  BookOpenCheckIcon,
  ExternalLinkIcon,
  FileTextIcon,
  GlobeIcon,
  ListTodoIcon,
  MoreVerticalIcon,
  NewspaperIcon,
  PaperclipIcon,
  PencilIcon,
  PlusIcon,
} from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { ReadingTaskDialog } from './ReadingTaskDialog'
import { SourceDialog } from './SourceDialog'
import {
  SOURCE_KIND_LABEL,
  SOURCE_STATUS_LABEL,
  type Source,
  type SourceKind,
  type SourceStatus,
  useSources,
  useUpdateSource,
} from './useSources'

const KIND_ICON: Record<SourceKind, typeof BookIcon> = {
  textbook: BookIcon,
  article: NewspaperIcon,
  website: GlobeIcon,
  other: FileTextIcon,
}

// Касание по статусу — следующий: прочитать → читаю → прочитано → прочитать
const NEXT_STATUS: Record<SourceStatus, SourceStatus> = { to_read: 'reading', reading: 'done', done: 'to_read' }

function SourceRow({
  source,
  onEdit,
  onReading,
}: {
  source: Source
  onEdit: () => void
  onReading: () => void
}) {
  const update = useUpdateSource(source.subject_id)
  const Icon = KIND_ICON[source.kind]
  const done = source.status === 'done'
  return (
    <li className="flex items-center gap-3 rounded-lg border px-3 py-2">
      <Icon className="size-5 shrink-0 text-muted-foreground" aria-label={SOURCE_KIND_LABEL[source.kind]} />
      <button type="button" onClick={onEdit} className="min-w-0 flex-1 text-left">
        <span className={cn('block text-sm font-medium', done && 'text-muted-foreground line-through')}>{source.title}</span>
        <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {source.author && <span>{source.author}</span>}
          {!source.required && <span>· дополнительная</span>}
          {source.files_count > 0 && (
            <span className="flex items-center gap-0.5">
              <PaperclipIcon className="size-3" /> файл
            </span>
          )}
        </span>
      </button>
      <Badge
        asChild
        variant={source.status === 'reading' ? 'default' : source.status === 'done' ? 'secondary' : 'outline'}
        className="cursor-pointer"
      >
        <button
          type="button"
          aria-label={`Статус: ${SOURCE_STATUS_LABEL[source.status]}. Сменить`}
          onClick={() => update.mutate({ id: source.id, body: { status: NEXT_STATUS[source.status] } })}
        >
          {source.status === 'done' && <BookOpenCheckIcon />}
          {SOURCE_STATUS_LABEL[source.status]}
        </button>
      </Badge>
      {source.url && (
        <Button asChild variant="ghost" size="icon" aria-label="Открыть ссылку">
          <a href={source.url} target="_blank" rel="noreferrer">
            <ExternalLinkIcon />
          </a>
        </Button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Ещё" className="-mr-2">
            <MoreVerticalIcon />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onReading}>
            <ListTodoIcon /> Задание: прочитать…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onEdit}>
            <PencilIcon /> Изменить, файл
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  )
}

/** Литература предмета: обязательная первой, статус — одним касанием, задание чтения из меню. */
export function SourceList({ subjectId }: { subjectId: string }) {
  const { data: sources, isPending, isError, error } = useSources(subjectId)
  const [editing, setEditing] = useState<Source | null>(null)
  const [creating, setCreating] = useState(false)
  const [reading, setReading] = useState<Source | null>(null)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button size="sm" variant="ghost" onClick={() => setCreating(true)}>
          <PlusIcon /> Источник
        </Button>
      </div>
      {isPending && <Skeleton className="h-24" />}
      {isError && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {sources && sources.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Список литературы пуст. Добавьте учебник, статью или сайт — из источника можно сразу сделать задание на чтение.
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {sources?.map((s) => (
          <SourceRow key={s.id} source={s} onEdit={() => setEditing(s)} onReading={() => setReading(s)} />
        ))}
      </ul>

      <SourceDialog open={creating} onOpenChange={setCreating} subjectId={subjectId} />
      <SourceDialog
        open={!!editing}
        onOpenChange={(open) => !open && setEditing(null)}
        subjectId={subjectId}
        source={editing ?? undefined}
      />
      <ReadingTaskDialog source={reading} onOpenChange={(open) => !open && setReading(null)} />
    </div>
  )
}
