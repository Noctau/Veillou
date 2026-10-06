import { DownloadIcon, FileIcon, FileTextIcon, Loader2Icon, PaperclipIcon, Trash2Icon } from 'lucide-react'
import { useRef } from 'react'

import { ConfirmButton } from '@/components/common/ConfirmButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import {
  type Attachment,
  type AttachmentOwner,
  useAttachments,
  useDeleteAttachment,
  useUploadAttachment,
} from './useAttachments'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`
}

const isImage = (a: Attachment) => /^image\/(png|jpeg|webp|gif)/.test(a.mime)

function Thumb({ attachment }: { attachment: Attachment }) {
  if (isImage(attachment)) {
    return <img src={attachment.url} alt="" loading="lazy" className="size-10 shrink-0 rounded-md border object-cover" />
  }
  const Icon = attachment.mime === 'application/pdf' || attachment.mime.startsWith('text/') ? FileTextIcon : FileIcon
  return (
    <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
      <Icon className="size-5 text-muted-foreground" />
    </span>
  )
}

type Props = { ownerType: AttachmentOwner; ownerId: string }

/** Файлы объекта: загрузка (несколько сразу), открыть, скачать, удалить. */
export function AttachmentList({ ownerType, ownerId }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const { data: attachments, isPending } = useAttachments(ownerType, ownerId)
  const upload = useUploadAttachment(ownerType, ownerId)
  const remove = useDeleteAttachment(ownerType, ownerId)

  const onFiles = async (files: FileList | null) => {
    for (const file of Array.from(files ?? [])) {
      await upload.mutateAsync(file).catch(() => undefined)
    }
    if (input.current) input.current.value = ''
  }

  return (
    <div className="flex flex-col gap-2">
      {isPending && <Skeleton className="h-12" />}
      {attachments && attachments.length > 0 && (
        <ul className="flex flex-col gap-1">
          {attachments.map((a) => (
            <li key={a.id} className="flex items-center gap-3 rounded-lg px-1 py-1 hover:bg-muted/50">
              <a href={a.url} target="_blank" rel="noreferrer" className="flex min-w-0 flex-1 items-center gap-3">
                <Thumb attachment={a} />
                <span className="min-w-0">
                  <span className="block truncate text-sm">{a.filename}</span>
                  <span className="block text-xs text-muted-foreground">{formatSize(a.size)}</span>
                </span>
              </a>
              <Button asChild variant="ghost" size="icon" aria-label="Скачать">
                <a href={a.download_url}>
                  <DownloadIcon />
                </a>
              </Button>
              <ConfirmButton title={`Удалить «${a.filename}»?`} onConfirm={() => remove.mutate(a.id)}>
                <Button variant="ghost" size="icon" aria-label="Удалить файл" className="text-muted-foreground">
                  <Trash2Icon />
                </Button>
              </ConfirmButton>
            </li>
          ))}
        </ul>
      )}
      <input ref={input} type="file" multiple hidden onChange={(e) => void onFiles(e.target.files)} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
      >
        {upload.isPending ? <Loader2Icon className="animate-spin" /> : <PaperclipIcon />}
        {upload.isPending ? 'Загружаем…' : 'Файл или фото'}
      </Button>
    </div>
  )
}
