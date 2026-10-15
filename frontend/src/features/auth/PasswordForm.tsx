import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/errors'

import { useChangePassword } from './useAuthMutations'

const MIN_PASSWORD = 8

const passwordSchema = z
  .object({
    current: z.string().min(1, 'Введите текущий пароль'),
    next: z.string().min(MIN_PASSWORD, `Не короче ${MIN_PASSWORD} символов`).max(1024, 'Слишком длинный'),
    repeat: z.string(),
  })
  .refine((v) => v.next === v.repeat, { path: ['repeat'], message: 'Пароли не совпадают' })
  .refine((v) => v.next !== v.current, { path: ['next'], message: 'Новый пароль совпадает с текущим' })

/** Смена пароля в настройках: текущий + новый дважды. */
export function PasswordForm() {
  const change = useChangePassword()
  const form = useForm({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current: '', next: '', repeat: '' },
  })
  const { errors } = form.formState

  const onSubmit = form.handleSubmit((v) =>
    change.mutate(
      { current_password: v.current, new_password: v.next },
      {
        onSuccess: () => {
          form.reset()
          toast.success('Пароль изменён', { description: 'На других устройствах нужно войти заново' })
        },
      },
    ),
  )

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Смена пароля">
      <FieldGroup>
        <Field data-invalid={!!errors.current}>
          <FieldLabel htmlFor="current-password">Текущий пароль</FieldLabel>
          <Input
            id="current-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!errors.current}
            {...form.register('current')}
          />
          <FieldError errors={[errors.current]} />
        </Field>
        <Field data-invalid={!!errors.next}>
          <FieldLabel htmlFor="new-password">Новый пароль</FieldLabel>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!errors.next}
            {...form.register('next')}
          />
          <FieldDescription>Не короче {MIN_PASSWORD} символов.</FieldDescription>
          <FieldError errors={[errors.next]} />
        </Field>
        <Field data-invalid={!!errors.repeat}>
          <FieldLabel htmlFor="repeat-password">Повторите новый пароль</FieldLabel>
          <Input
            id="repeat-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!errors.repeat}
            {...form.register('repeat')}
          />
          <FieldError errors={[errors.repeat]} />
        </Field>
        {change.isError && <FieldError>{errorMessage(change.error)}</FieldError>}
        <Button type="submit" className="self-start" disabled={change.isPending}>
          {change.isPending ? 'Меняем…' : 'Сменить пароль'}
        </Button>
      </FieldGroup>
    </form>
  )
}
