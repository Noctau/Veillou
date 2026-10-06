import { FileTextIcon, XIcon } from 'lucide-react'
import { useEffect, useMemo } from 'react'

/** Превью файлов из «Поделиться» с кнопкой «убрать». */
export function SharedFiles({ files, onRemove }: { files: File[]; onRemove: (index: number) => void }) {
  const previews = useMemo(
    () => files.map((f) => (f.type.startsWith('image/') ? URL.createObjectURL(f) : null)),
    [files],
  )
  useEffect(() => () => previews.forEach((url) => url && URL.revokeObjectURL(url)), [previews])

  return (
    <ul className="flex gap-2 overflow-x-auto pb-1" aria-label="Файлы">
      {files.map((file, i) => (
        <li key={`${file.name}-${i}`} className="relative size-20 shrink-0 overflow-hidden rounded-lg border bg-muted">
          {previews[i] ? (
            <img src={previews[i]} alt={file.name} className="size-full object-cover" />
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-1 p-1 text-center">
              <FileTextIcon className="size-6 text-muted-foreground" />
              <span className="line-clamp-2 text-[10px] leading-tight break-all">{file.name}</span>
            </div>
          )}
          <button
            type="button"
            onClick={() => onRemove(i)}
            aria-label={`Убрать ${file.name}`}
            className="absolute top-1 right-1 rounded-full bg-background/80 p-0.5"
          >
            <XIcon className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  )
}
