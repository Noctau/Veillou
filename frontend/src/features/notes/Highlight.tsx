import { HIT_END, HIT_START } from './useSearch'

/** Сниппет поиска: совпадения (между маркерами) — выделены. Без HTML из ответа. */
export function Highlight({ text }: { text: string }) {
  const parts = text.split(HIT_START)
  return (
    <>
      {parts.map((part, i) => {
        if (i === 0) return <span key={i}>{part}</span>
        const [hit, rest = ''] = part.split(HIT_END)
        return (
          <span key={i}>
            <mark className="rounded-sm bg-amber-300/40 px-0.5 text-foreground">{hit}</mark>
            {rest}
          </span>
        )
      })}
    </>
  )
}
