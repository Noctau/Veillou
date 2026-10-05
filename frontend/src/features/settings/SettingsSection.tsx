import type { FormEventHandler, ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { FieldGroup } from '@/components/ui/field'

type Props = {
  title: string
  description?: string
  onSubmit: FormEventHandler<HTMLFormElement>
  isDirty: boolean
  isSaving: boolean
  children: ReactNode
}

export function SettingsSection({ title, description, onSubmit, isDirty, isSaving, children }: Props) {
  return (
    <Card>
      <form onSubmit={onSubmit} noValidate>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="pt-4">
          <FieldGroup>{children}</FieldGroup>
        </CardContent>
        <CardFooter className="justify-end pt-4">
          <Button type="submit" disabled={!isDirty || isSaving}>
            {isSaving ? 'Сохраняем…' : 'Сохранить'}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
