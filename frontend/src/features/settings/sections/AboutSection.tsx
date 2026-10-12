import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { ABOUT_UI as T, ABOUT_MAX } from '@/lib/terms'

import { SettingsSection } from '../SettingsSection'
import { useUpdateSettings, type UserSettings } from '../useSettings'

const schema = z.object({ about: z.string().max(ABOUT_MAX, T.tooLong) })

/** «О себе» — контекст для ИИ: разбивка, разбор текста и фото, этапы, настройка. */
export function AboutSection({ settings }: { settings: UserSettings }) {
  const update = useUpdateSettings()
  const form = useForm({ resolver: zodResolver(schema), values: { about: settings.about } })
  const { errors, isDirty } = form.formState
  const length = useWatch({ control: form.control, name: 'about' }).length

  return (
    <SettingsSection
      title={T.title}
      description={T.description}
      onSubmit={form.handleSubmit((values) => update.mutate({ about: values.about.trim() }))}
      isDirty={isDirty}
      isSaving={update.isPending}
    >
      <AboutField id="about" error={errors.about?.message} length={length} {...form.register('about')} />
    </SettingsSection>
  )
}

type AboutFieldProps = React.ComponentProps<typeof Textarea> & { error?: string; length: number }

export function AboutField({ id, error, length, ...props }: AboutFieldProps) {
  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={id}>{T.label}</FieldLabel>
      <Textarea id={id} rows={4} placeholder={T.placeholder} aria-invalid={!!error} {...props} />
      <FieldDescription>
        {T.hint} {length}/{ABOUT_MAX}
      </FieldDescription>
      {error && <FieldError>{error}</FieldError>}
    </Field>
  )
}
