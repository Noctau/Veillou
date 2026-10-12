import { ExternalLinkIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

import { formatLink, type LinkValue, renderFields } from './fields'
import type { Area, FieldDef, FieldValues } from './useAreas'

function Links({ value, multiple }: { value: unknown; multiple: boolean }) {
  const items = (multiple && Array.isArray(value) ? value : [value]) as (LinkValue | string)[]
  return (
    <span className="inline-flex flex-wrap gap-x-3 gap-y-1">
      {items.map((l, i) => {
        const url = typeof l === 'string' ? l : l.url
        return (
          <a
            key={i}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="relative z-10 inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
          >
            {formatLink(l)}
            <ExternalLinkIcon className="size-3" />
          </a>
        )
      })}
    </span>
  )
}

/** Значения полей (сферы, события): «Подпись: значение», ссылки — кликабельные. */
export function FieldValuesView({
  defs,
  values,
  areas,
  className,
}: {
  defs: FieldDef[]
  values: FieldValues
  /** Для полей «сфера» — названия. */
  areas?: Area[]
  className?: string
}) {
  const areaNames = Object.fromEntries((areas ?? []).map((a) => [a.id, a.name]))
  const rendered = renderFields(defs, values, { areaNames })
  if (!rendered.length) return null
  return (
    <dl className={cn('flex flex-col gap-0.5 text-sm', className)}>
      {rendered.map(({ def, text, value }) => (
        <div key={def.id} className="flex min-w-0 gap-1.5">
          <dt className="shrink-0 text-muted-foreground">{def.label}:</dt>
          <dd className="min-w-0">
            {def.type === 'link' ? <Links value={value} multiple={def.multiple} /> : <span className="break-words">{text}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}
