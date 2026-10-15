import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'

import { PasswordForm } from './PasswordForm'

function setup() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PasswordForm />
    </QueryClientProvider>,
  )
  const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
  const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Сменить пароль' }))
  return { fill, submit }
}

describe('смена пароля', () => {
  afterEach(cleanup)

  it('проверяет поля до отправки', async () => {
    const post = vi.spyOn(api, 'POST')
    const { fill, submit } = setup()
    fill('Текущий пароль', 'old-password')
    fill('Новый пароль', 'short')
    fill('Повторите новый пароль', 'other')
    submit()
    expect(await screen.findByText('Не короче 8 символов')).toBeTruthy()
    expect(await screen.findByText('Пароли не совпадают')).toBeTruthy()
    expect(post).not.toHaveBeenCalled()
  })

  it('отправляет текущий и новый пароль', async () => {
    const post = vi
      .spyOn(api, 'POST')
      .mockResolvedValue({ data: undefined, error: undefined, response: new Response() } as never)
    const { fill, submit } = setup()
    fill('Текущий пароль', 'old-password')
    fill('Новый пароль', 'new-password-42')
    fill('Повторите новый пароль', 'new-password-42')
    submit()
    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(post.mock.calls[0]).toEqual([
      '/api/v1/me/password',
      { body: { current_password: 'old-password', new_password: 'new-password-42' } },
    ])
  })

  it('показывает ошибку сервера', async () => {
    vi.spyOn(api, 'POST').mockResolvedValue({
      data: undefined,
      error: { error: { code: 'wrong_password', message: 'Текущий пароль неверный' } },
      response: new Response(null, { status: 400 }),
    } as never)
    const { fill, submit } = setup()
    fill('Текущий пароль', 'wrong-password')
    fill('Новый пароль', 'new-password-42')
    fill('Повторите новый пароль', 'new-password-42')
    submit()
    expect(await screen.findByText('Текущий пароль неверный')).toBeTruthy()
  })
})
