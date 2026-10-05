import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/errors'

import { useLogin } from './useAuthMutations'

const schema = z.object({
  email: z.email('Введите email'),
  password: z.string().min(1, 'Введите пароль'),
})

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const login = useLogin()
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })
  const { errors } = form.formState

  const onSubmit = form.handleSubmit((values) => login.mutate(values, { onSuccess }))

  return (
    <form onSubmit={onSubmit} noValidate>
      <FieldGroup>
        <Field data-invalid={!!errors.email}>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            aria-invalid={!!errors.email}
            {...form.register('email')}
          />
          <FieldError errors={[errors.email]} />
        </Field>
        <Field data-invalid={!!errors.password}>
          <FieldLabel htmlFor="password">Пароль</FieldLabel>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!errors.password}
            {...form.register('password')}
          />
          <FieldError errors={[errors.password]} />
        </Field>
        {login.isError && <FieldError>{errorMessage(login.error)}</FieldError>}
        <Button type="submit" size="lg" disabled={login.isPending}>
          {login.isPending ? 'Входим…' : 'Войти'}
        </Button>
      </FieldGroup>
    </form>
  )
}
