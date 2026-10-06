import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  CameraIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  ImagesIcon,
  Loader2Icon,
  RotateCcwIcon,
  RotateCwIcon,
  Trash2Icon,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  type Attachment,
  useDeleteAttachment,
  useReorderAttachments,
  useReplaceAttachment,
  useUploadAttachment,
} from '@/features/attachments/useAttachments'
import { compressImage, rotateImage } from '@/lib/image'
import { cn } from '@/lib/utils'

import { isPageImage } from './labels'

function Thumb({ page, index, onOpen }: { page: Attachment; index: number; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: page.id })
  return (
    <li
      ref={setNodeRef}
      // Исключение из «без inline style»: dnd-kit двигает элемент через transform
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn('relative touch-manipulation', isDragging && 'z-10 opacity-80')}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Страница ${index + 1}`}
        className="block aspect-[3/4] w-full cursor-grab overflow-hidden rounded-lg border bg-muted active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <img src={page.url} alt="" loading="lazy" className="size-full object-cover" draggable={false} />
      </button>
      <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-background/80 px-1.5 text-xs tabular-nums">
        {index + 1}
      </span>
    </li>
  )
}

function Viewer({
  pages,
  index,
  onIndex,
  onClose,
  noteId,
}: {
  pages: Attachment[]
  index: number | null
  onIndex: (i: number) => void
  onClose: () => void
  noteId: string
}) {
  const replace = useReplaceAttachment('note', noteId)
  const remove = useDeleteAttachment('note', noteId)
  const [rotating, setRotating] = useState(false)
  const page = index !== null ? pages[index] : undefined

  const rotate = async (degrees: 90 | -90) => {
    if (!page) return
    setRotating(true)
    try {
      const blob = await (await fetch(page.url)).blob()
      await replace.mutateAsync({ id: page.id, file: await rotateImage(blob, page.filename, degrees) })
    } catch {
      toast.error('Не удалось повернуть страницу')
    } finally {
      setRotating(false)
    }
  }

  return (
    <Dialog open={!!page} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[95dvh] flex-col gap-3 p-3 sm:max-w-3xl">
        {page && index !== null && (
          <>
            <DialogTitle className="text-sm font-normal text-muted-foreground">
              Страница {index + 1} из {pages.length}
            </DialogTitle>
            <DialogDescription className="sr-only">{page.filename}</DialogDescription>
            <div className="relative flex min-h-0 flex-1 items-center justify-center">
              <img
                key={page.url}
                src={page.url}
                alt={`Страница ${index + 1}`}
                className={cn('max-h-[75dvh] max-w-full rounded-md object-contain', rotating && 'opacity-50')}
              />
              {rotating && <Loader2Icon className="absolute size-8 animate-spin" />}
            </div>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" aria-label="Предыдущая" disabled={index === 0} onClick={() => onIndex(index - 1)}>
                <ChevronLeftIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Следующая"
                disabled={index === pages.length - 1}
                onClick={() => onIndex(index + 1)}
              >
                <ChevronRightIcon />
              </Button>
              <div className="ml-auto flex gap-1">
                <Button variant="ghost" size="icon" aria-label="Повернуть влево" disabled={rotating} onClick={() => void rotate(-90)}>
                  <RotateCcwIcon />
                </Button>
                <Button variant="ghost" size="icon" aria-label="Повернуть вправо" disabled={rotating} onClick={() => void rotate(90)}>
                  <RotateCwIcon />
                </Button>
                <Button asChild variant="ghost" size="icon" aria-label="Скачать">
                  <a href={page.download_url}>
                    <DownloadIcon />
                  </a>
                </Button>
                <ConfirmButton
                  title={`Удалить страницу ${index + 1}?`}
                  onConfirm={() => {
                    remove.mutate(page.id)
                    if (pages.length === 1) onClose()
                    else onIndex(Math.min(index, pages.length - 2))
                  }}
                >
                  <Button variant="ghost" size="icon" aria-label="Удалить страницу" className="text-destructive">
                    <Trash2Icon />
                  </Button>
                </ConfirmButton>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

type Props = { noteId: string; attachments: Attachment[] }

/** Страницы фото-конспекта: съёмка камерой, галерея, порядок перетаскиванием, просмотр. */
export function NotePages({ noteId, attachments }: Props) {
  const camera = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)
  const upload = useUploadAttachment('note', noteId)
  const reorder = useReorderAttachments('note', noteId)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [opened, setOpened] = useState<number | null>(null)

  const pages = attachments.filter(isPageImage)
  const others = attachments.filter((a) => !isPageImage(a))

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const ids = pages.map((p) => p.id)
    const moved = arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id)))
    reorder.mutate([...moved, ...others.map((a) => a.id)])
  }

  const onFiles = async (input: HTMLInputElement) => {
    const files = Array.from(input.files ?? [])
    input.value = ''
    if (!files.length) return
    setProgress({ done: 0, total: files.length })
    // По одной и по порядку — страницы встают в том порядке, в каком выбраны
    for (const [i, file] of files.entries()) {
      try {
        await upload.mutateAsync(await compressImage(file))
      } catch {
        // ошибку уже показал toast мутации
      }
      setProgress({ done: i + 1, total: files.length })
    }
    setProgress(null)
  }

  return (
    <div className="flex flex-col gap-3">
      {pages.length > 0 && (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={pages.map((p) => p.id)} strategy={rectSortingStrategy}>
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
              {pages.map((p, i) => (
                <Thumb key={p.id} page={p} index={i} onOpen={() => setOpened(i)} />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}
      {pages.length > 1 && (
        <p className="text-xs text-muted-foreground">Порядок — перетаскиванием (на телефоне — подержать и тянуть).</p>
      )}

      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={(e) => void onFiles(e.currentTarget)} />
      <input ref={gallery} type="file" accept="image/*" multiple hidden onChange={(e) => void onFiles(e.currentTarget)} />
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={!!progress} onClick={() => camera.current?.click()}>
          <CameraIcon /> {pages.length ? 'Ещё страница' : 'Снять страницу'}
        </Button>
        <Button type="button" variant="outline" disabled={!!progress} onClick={() => gallery.current?.click()}>
          <ImagesIcon /> Из галереи
        </Button>
        {progress && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Загружаем {Math.min(progress.done + 1, progress.total)} из {progress.total}
          </span>
        )}
      </div>

      <Viewer pages={pages} index={opened} onIndex={setOpened} onClose={() => setOpened(null)} noteId={noteId} />
    </div>
  )
}
