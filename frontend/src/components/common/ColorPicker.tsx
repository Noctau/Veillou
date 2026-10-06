import { CheckIcon } from 'lucide-react'

import { PALETTE } from '@/lib/colors'
import { cn } from '@/lib/utils'

type Props = {
  value: string | null | undefined
  onChange: (hex: string) => void
  id?: string
}

export function ColorPicker({ value, onChange, id }: Props) {
  return (
    <div id={id} role="radiogroup" className="flex flex-wrap gap-2">
      {PALETTE.map((c) => {
        const selected = value?.toLowerCase() === c.hex
        return (
          <button
            key={c.hex}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={c.name}
            onClick={() => onChange(c.hex)}
            className={cn(
              'flex size-8 items-center justify-center rounded-full ring-offset-2 ring-offset-background transition',
              c.bg,
              selected && 'ring-2 ring-foreground',
            )}
          >
            {selected && <CheckIcon className="size-4 text-white" />}
          </button>
        )
      })}
    </div>
  )
}
