import { EyeIcon, HeadingIcon, ListIcon, PencilIcon, SigmaIcon, SquareFunctionIcon } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

import { Markdown } from './Markdown'

const SAVE_DELAY_MS = 800

type Snippet = { label: string; icon: typeof SigmaIcon; before: string; after: string; line?: boolean }

// На телефоне $ и # далеко — вставляем одной кнопкой
const SNIPPETS: Snippet[] = [
  { label: 'Заголовок', icon: HeadingIcon, before: '## ', after: '', line: true },
  { label: 'Список', icon: ListIcon, before: '- ', after: '', line: true },
  { label: 'Формула в строке', icon: SigmaIcon, before: '$', after: '$' },
  { label: 'Формула отдельно', icon: SquareFunctionIcon, before: '\n$$\n', after: '\n$$\n' },
]

type Props = {
  value: string
  onSave: (value: string) => void
  autoFocus?: boolean
}

/** Markdown + LaTeX: на телефоне — «Текст / Просмотр», на ноутбуке — рядом. Сохраняет сам. */
export function NoteTextEditor({ value, onSave, autoFocus }: Props) {
  const [text, setText] = useState(value)
  const [mode, setMode] = useState<'edit' | 'view'>(value.trim() ? 'view' : 'edit')
  const [dirty, setDirty] = useState(false)
  const area = useRef<HTMLTextAreaElement>(null)
  const saved = useRef(value)
  const timer = useRef<number | undefined>(undefined)

  const flush = (next = text) => {
    window.clearTimeout(timer.current)
    setDirty(false)
    if (next !== saved.current) {
      saved.current = next
      onSave(next)
    }
  }

  const change = (next: string) => {
    setText(next)
    setDirty(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => flush(next), SAVE_DELAY_MS)
  }

  // Ушли со страницы, не дождавшись автосохранения, — сохраняем сразу
  const flushRef = useRef(flush)
  useLayoutEffect(() => {
    flushRef.current = flush
  })
  useEffect(() => () => flushRef.current(), [])

  const insert = ({ before, after, line }: Snippet) => {
    const el = area.current
    if (!el) return
    const { selectionStart: start, selectionEnd: end } = el
    const lineStart = text.lastIndexOf('\n', start - 1) + 1
    const at = line ? lineStart : start
    const selected = text.slice(start, end)
    const next = line
      ? text.slice(0, at) + before + text.slice(at)
      : text.slice(0, start) + before + selected + after + text.slice(end)
    change(next)
    requestAnimationFrame(() => {
      el.focus()
      const cursor = line ? end + before.length : start + before.length + selected.length
      el.setSelectionRange(cursor, cursor)
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={mode}
          onValueChange={(v) => v && setMode(v as 'edit' | 'view')}
          className="lg:hidden"
        >
          <ToggleGroupItem value="edit" className="gap-1">
            <PencilIcon /> Текст
          </ToggleGroupItem>
          <ToggleGroupItem value="view" className="gap-1">
            <EyeIcon /> Просмотр
          </ToggleGroupItem>
        </ToggleGroup>
        <div className={cn('flex gap-0.5', mode === 'view' && 'max-lg:hidden')}>
          {SNIPPETS.map((s) => (
            <Button
              key={s.label}
              type="button"
              variant="ghost"
              size="icon"
              aria-label={s.label}
              title={s.label}
              onMouseDown={(e) => e.preventDefault()} // не терять выделение в поле
              onClick={() => insert(s)}
            >
              <s.icon />
            </Button>
          ))}
        </div>
        <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">
          {dirty ? 'Сохраняем…' : 'Сохранено'}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Textarea
          ref={area}
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => change(e.target.value)}
          onBlur={() => flush()}
          placeholder={'# Тема лекции\n\nТекст, списки, формулы: $p = \\rho R T$\n\n$$\n\\frac{dp}{dz} = -\\rho g\n$$'}
          aria-label="Текст конспекта"
          className={cn('min-h-72 font-mono text-sm lg:min-h-[28rem]', mode === 'view' && 'max-lg:hidden')}
        />
        <div
          className={cn(
            'min-h-24 rounded-lg border px-3 py-2 lg:max-h-[70dvh] lg:overflow-y-auto',
            mode === 'edit' && 'max-lg:hidden',
          )}
        >
          {text.trim() ? (
            <Markdown>{text}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground">Пока пусто.</p>
          )}
        </div>
      </div>
    </div>
  )
}
