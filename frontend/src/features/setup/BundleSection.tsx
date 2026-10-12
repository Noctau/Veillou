import { DownloadIcon, SparklesIcon, UploadIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errorMessage } from '@/lib/errors'
import { BUNDLE_UI as T, SETUP_UI } from '@/lib/terms'

import { type BundleInput, exportBundle, type ImportResult, useImportBundle } from './useSetup'

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

/** Настройки → «Настройка целиком»: по описанию (ИИ), скачать сборку, загрузить из файла. */
export function BundleSection() {
  const fileRef = useRef<HTMLInputElement>(null)
  const importBundle = useImportBundle()
  const [pending, setPending] = useState<{ bundle: BundleInput; preview: ImportResult } | null>(null)

  const onExport = async () => {
    try {
      const bundle = await exportBundle()
      download(`veillou-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(bundle, null, 2))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const onFile = async (file: File) => {
    let bundle: BundleInput
    try {
      bundle = JSON.parse(await file.text())
    } catch {
      toast.error(T.badFile)
      return
    }
    importBundle.mutate({ bundle, dryRun: true }, { onSuccess: (preview) => setPending({ bundle, preview }) })
  }

  const changes = pending ? [...pending.preview.added, ...pending.preview.changed] : []

  return (
    <Card>
      <CardHeader>
        <CardTitle>{T.title}</CardTitle>
        <CardDescription>{T.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2 pt-2">
        <Button asChild>
          <Link to="/setup">
            <SparklesIcon /> {T.setup}
          </Link>
        </Button>
        <Button variant="outline" onClick={onExport}>
          <DownloadIcon /> {T.export}
        </Button>
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={importBundle.isPending}>
          <UploadIcon /> {T.import}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ''
            if (file) onFile(file)
          }}
        />
      </CardContent>
      <Dialog open={!!pending} onOpenChange={(open) => !open && setPending(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{T.preview}</DialogTitle>
          </DialogHeader>
          {changes.length === 0 ? (
            <p className="text-sm text-muted-foreground">{T.nothing}</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {pending?.preview.added.map((c) => (
                <li key={`a-${c.section}-${c.ref}`}>
                  <span className="text-muted-foreground">{T.added} · {SETUP_UI.section[c.section] ?? c.section}:</span> {c.name}
                </li>
              ))}
              {pending?.preview.changed.map((c) => (
                <li key={`c-${c.section}-${c.ref}`}>
                  <span className="text-muted-foreground">{T.changed} · {SETUP_UI.section[c.section] ?? c.section}:</span> {c.name}
                </li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPending(null)}>
              {T.cancel}
            </Button>
            <Button
              disabled={!changes.length || importBundle.isPending}
              onClick={() =>
                pending &&
                importBundle.mutate(
                  { bundle: pending.bundle, dryRun: false },
                  {
                    onSuccess: (r) => {
                      toast.success(SETUP_UI.applied(r.added.length, r.changed.length))
                      setPending(null)
                    },
                  },
                )
              }
            >
              {T.apply}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
