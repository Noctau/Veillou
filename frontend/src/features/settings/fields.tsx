import type { ComponentProps } from 'react'

import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'

type InputProps = Omit<ComponentProps<'input'>, 'type'>

type RangeProps = {
  label: string
  description?: string
  start: InputProps
  end: InputProps
  error?: string
}

/** «с — до» из двух полей времени. */
export function TimeRangeField({ label, description, start, end, error }: RangeProps) {
  return (
    <Field data-invalid={!!error}>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex items-center gap-2">
        <Input type="time" step={300} aria-label={`${label}: с`} aria-invalid={!!error} {...start} />
        <span className="text-muted-foreground">—</span>
        <Input type="time" step={300} aria-label={`${label}: до`} aria-invalid={!!error} {...end} />
      </div>
      {description && <FieldDescription>{description}</FieldDescription>}
      {error && <FieldError>{error}</FieldError>}
    </Field>
  )
}

type SingleProps = InputProps & {
  label: string
  description?: string
  error?: string
  suffix?: string
}

export function TimeField({ label, description, error, id, ...props }: SingleProps) {
  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input id={id} type="time" step={300} aria-invalid={!!error} {...props} />
      {description && <FieldDescription>{description}</FieldDescription>}
      {error && <FieldError>{error}</FieldError>}
    </Field>
  )
}

export function NumberField({ label, description, error, suffix, id, ...props }: SingleProps) {
  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" inputMode="decimal" className="w-28" aria-invalid={!!error} {...props} />
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </div>
      {description && <FieldDescription>{description}</FieldDescription>}
      {error && <FieldError>{error}</FieldError>}
    </Field>
  )
}
