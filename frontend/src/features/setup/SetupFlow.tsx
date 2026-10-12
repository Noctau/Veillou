import { AlertTriangleIcon, Loader2Icon, PencilIcon, RefreshCwIcon, SparklesIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { jobResult, useJob } from '@/features/ai/useJob'
import { useUpdateSettings } from '@/features/settings/useSettings'
import { ONBOARDING_UI, SETUP_UI as T } from '@/lib/terms'

import { itemSummary, itemTitle, previousLines, removeItem, type Section, SECTIONS } from './describe'
import { type Bundle, type SetupDraft, useImportBundle, useStartSetup } from './useSetup'

type Item = { ref: string } & Record<string, unknown>

/** Поля, которые можно поправить прямо в карточке (остальное — потом в Настройках). */
const EDITABLE: Partial<Record<Section, { key: string; label: string; type: 'text' | 'time' | 'number' }[]>> = {
  event_types: [{ key: 'name', label: T.name, type: 'text' }],
  area_types: [{ key: 'name', label: T.name, type: 'text' }],
  areas: [{ key: 'name', label: T.name, type: 'text' }],
  task_types: [{ key: 'name', label: T.name, type: 'text' }],
  schedule_rules: [
    { key: 'start_time', label: T.start_time, type: 'time' },
    { key: 'end_time', label: T.end_time, type: 'time' },
  ],
  day_profiles: [
    { key: 'name', label: T.name, type: 'text' },
    { key: 'wake', label: T.wakeLabel, type: 'time' },
    { key: 'sleep', label: T.sleepLabel, type: 'time' },
  ],
  budgets: [
    { key: 'name', label: T.name, type: 'text' },
    { key: 'minutes_per_day', label: T.minutes, type: 'number' },
  ],
}

function BrickCard({
  section,
  item,
  status,
  onChange,
  onRemove,
}: {
  section: Section
  item: Item
  status?: string
  onChange: (item: Item) => void
  onRemove: () => void
}) {
  const [editing, setEditing] = useState(false)
  const fields = EDITABLE[section]
  const summary = itemSummary(section, item)
  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {itemTitle(item)}
            {status && (
              <Badge variant={status === 'added' ? 'default' : 'secondary'} className="font-normal">
                {T.status[status]}
              </Badge>
            )}
          </div>
          {summary && <div className="text-xs text-muted-foreground">{summary}</div>}
        </div>
        {fields && (
          <Button variant="ghost" size="icon" aria-label={T.edit} onClick={() => setEditing((v) => !v)}>
            <PencilIcon />
          </Button>
        )}
        <Button variant="ghost" size="icon" aria-label={T.remove} className="text-destructive" onClick={onRemove}>
          <Trash2Icon />
        </Button>
      </div>
      {editing && fields && (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {fields.map((f) => (
            <Field key={f.key} className="w-auto">
              <FieldLabel htmlFor={`${item.ref}-${f.key}`}>{f.label}</FieldLabel>
              <Input
                id={`${item.ref}-${f.key}`}
                type={f.type}
                className={f.type === 'text' ? 'w-48' : 'w-28'}
                value={String(item[f.key] ?? '')}
                onChange={(e) =>
                  onChange({ ...item, [f.key]: f.type === 'number' ? Number(e.target.value) || 0 : e.target.value })
                }
              />
            </Field>
          ))}
          <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
            {T.done}
          </Button>
        </div>
      )}
    </li>
  )
}

function Review({ draft, onRedo, onApplied }: { draft: SetupDraft; onRedo: (comment: string, bundle: Bundle) => void; onApplied: () => void }) {
  const [bundle, setBundle] = useState<Bundle>(draft.bundle)
  const [saveAbout, setSaveAbout] = useState(!!draft.about)
  const [about, setAbout] = useState(draft.about)
  const [comment, setComment] = useState('')
  const importBundle = useImportBundle()
  const updateSettings = useUpdateSettings()

  const status = new Map<string, string>()
  for (const kind of ['added', 'changed', 'skipped'] as const) {
    for (const c of draft.preview[kind]) status.set(`${c.section}/${c.ref}`, kind)
  }
  const sections = SECTIONS.filter((s) => (bundle[s] as Item[]).length > 0)

  const apply = () =>
    importBundle.mutate(
      { bundle, dryRun: false },
      {
        onSuccess: (result) => {
          if (saveAbout && about.trim()) updateSettings.mutate({ about: about.trim() })
          toast.success(T.applied(result.added.length, result.changed.length))
          onApplied()
        },
      },
    )

  return (
    <div className="flex flex-col gap-4">
      {draft.warnings.length > 0 && (
        <Card>
          <CardContent className="flex flex-col gap-1.5 py-4">
            <div className="text-sm font-medium">{T.warnings}</div>
            {draft.warnings.map((w) => (
              <p key={w} className="flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
                <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
                {w}
              </p>
            ))}
          </CardContent>
        </Card>
      )}
      {sections.length === 0 && <p className="text-sm text-muted-foreground">{T.empty}</p>}
      {sections.map((section) => (
        <section key={section} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">{T.section[section]}</h2>
          <ul className="flex flex-col gap-2">
            {(bundle[section] as Item[]).map((item) => (
              <BrickCard
                key={item.ref}
                section={section}
                item={item}
                status={status.get(`${section}/${item.ref}`)}
                onChange={(next) =>
                  setBundle((b) => ({
                    ...b,
                    [section]: (b[section] as Item[]).map((i) => (i.ref === item.ref ? next : i)),
                  }))
                }
                onRemove={() => setBundle((b) => removeItem(b, section, item.ref))}
              />
            ))}
          </ul>
        </section>
      ))}
      {draft.about && (
        <Field>
          <div className="flex items-center gap-2">
            <Checkbox id="setup-about" checked={saveAbout} onCheckedChange={(v) => setSaveAbout(v === true)} />
            <FieldLabel htmlFor="setup-about">{T.about}</FieldLabel>
          </div>
          {saveAbout && <Textarea rows={2} value={about} onChange={(e) => setAbout(e.target.value)} />}
        </Field>
      )}
      <Field>
        <FieldLabel htmlFor="setup-comment">{T.comment}</FieldLabel>
        <div className="flex gap-2">
          <Input
            id="setup-comment"
            value={comment}
            placeholder={T.commentPlaceholder}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button variant="outline" disabled={!comment.trim()} onClick={() => onRedo(comment.trim(), bundle)}>
            <RefreshCwIcon /> <span className="hidden sm:inline">{T.redo}</span>
          </Button>
        </div>
      </Field>
      <Button onClick={apply} disabled={importBundle.isPending || sections.length === 0}>
        {importBundle.isPending ? T.applying : T.apply}
      </Button>
    </div>
  )
}

function Thinking({ waiting }: { waiting?: string | null }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-6 text-sm" aria-live="polite">
        <Loader2Icon className="size-5 shrink-0 animate-spin text-primary" />
        <div>
          <div>{waiting ?? T.thinking}</div>
          <div className="text-xs text-muted-foreground">{T.thinkingHint}</div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * ИИ-настройка (M21.4): описание → черновик сборки → проверка (правка, удаление,
 * «Заново с комментарием») → «Применить» = импорт. Id джобы — в адресе (`?setupJob=`),
 * так что перезагрузка открывает тот же черновик.
 */
export function SetupFlow({
  onApplied,
  manual,
  intro = true,
}: {
  onApplied: () => void
  manual?: (text: string) => void
  intro?: boolean
}) {
  const [params, setParams] = useSearchParams()
  const jobId = params.get('setupJob')
  const [text, setText] = useState('')
  const start = useStartSetup()
  const { data: job } = useJob(jobId)
  const draft = jobResult(job, 'setup')

  const setJob = (id: string | null) =>
    setParams(
      (old) => {
        const next = new URLSearchParams(old)
        if (id) next.set('setupJob', id)
        else next.delete('setupJob')
        return next
      },
      { replace: true },
    )

  const run = (body: { comment?: string; previous?: string[] } = {}) =>
    start.mutate(
      { text: text.trim(), comment: body.comment ?? null, previous: body.previous ?? [] },
      { onSuccess: (id) => setJob(id) },
    )

  if (jobId && job?.status !== 'failed' && !draft) return <Thinking waiting={job?.waiting} />

  if (draft) {
    return (
      <Review
        key={jobId}
        draft={draft}
        onRedo={(comment, bundle) =>
          start.mutate(
            { text: draft.text, comment, previous: previousLines(bundle) },
            { onSuccess: (id) => setJob(id) },
          )
        }
        onApplied={onApplied}
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {intro && <p className="text-sm text-muted-foreground">{T.intro}</p>}
      {job?.status === 'failed' && (
        <p className="text-sm text-destructive">
          {T.failed}: {job.error}
        </p>
      )}
      <Field>
        <FieldLabel htmlFor="setup-text">{T.label}</FieldLabel>
        <Textarea
          id="setup-text"
          rows={4}
          maxLength={4000}
          placeholder={T.placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!text.trim() || start.isPending} onClick={() => run()}>
          <SparklesIcon /> {job?.status === 'failed' ? T.retry : T.start}
        </Button>
        {manual && (
          <Button variant="outline" onClick={() => manual(text.trim())}>
            {ONBOARDING_UI.manual}
          </Button>
        )}
      </div>
    </div>
  )
}
