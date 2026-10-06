import { useEffect, useState } from 'react'

import { deleteShare, loadShare, shareText } from '@/lib/pwa-shared'

/**
 * То, что пришло через «Поделиться» (service worker положил в IndexedDB, в URL — ?share=<id>).
 * Текст уходит в строку быстрого ввода, файлы — в превью.
 */
export function useShare(shareId: string | null, setText: (text: string) => void) {
  const [files, setFiles] = useState<File[]>([])

  useEffect(() => {
    if (!shareId) return
    let cancelled = false
    void loadShare(shareId).then((item) => {
      if (cancelled || !item) return
      setFiles(item.files)
      const text = shareText(item)
      if (text) setText(text)
    })
    return () => {
      cancelled = true
    }
  }, [shareId, setText])

  const removeFile = (index: number) => setFiles((old) => old.filter((_, i) => i !== index))

  /** Сохранено — больше не нужно. */
  const finish = () => {
    setFiles([])
    if (shareId) void deleteShare(shareId)
  }

  return { files, removeFile, finish }
}
