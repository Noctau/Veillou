import { act, cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

import { setSpellcheckEnabled, spellcheckProps } from './spellcheck'

describe('проверка правописания', () => {
  afterEach(() => {
    cleanup()
    setSpellcheckEnabled(true)
  })

  it('включена в текстовых полях и выключена в адресах, числах и паролях', () => {
    expect(spellcheckProps(undefined, {}, true)).toEqual({ spellCheck: true, lang: 'ru', autoCorrect: 'on' })
    expect(spellcheckProps('text', {}, true).spellCheck).toBe(true)
    for (const type of ['email', 'password', 'number', 'date', 'time', 'url']) {
      expect(spellcheckProps(type, {}, true).spellCheck).toBe(false)
    }
    expect(spellcheckProps('text', { autoComplete: 'email' }, true).spellCheck).toBe(false)
  })

  it('своё значение поля главнее, выключатель — для всех полей', () => {
    expect(spellcheckProps(undefined, { spellCheck: false }, true).spellCheck).toBe(false)
    expect(spellcheckProps(undefined, { lang: 'en' }, true).lang).toBe('en')
    expect(spellcheckProps(undefined, {}, false)).toMatchObject({ spellCheck: false, autoCorrect: 'off' })
  })

  it('поля ввода получают атрибуты и следуют за выключателем', () => {
    const { container } = render(
      <>
        <Input aria-label="title" />
        <Input type="email" aria-label="email" />
        <Textarea aria-label="body" />
      </>,
    )
    const [title, email] = Array.from(container.querySelectorAll('input'))
    const body = container.querySelector('textarea')!
    // jsdom не знает свойство .spellcheck — смотрим атрибут
    const spell = (el: Element) => el.getAttribute('spellcheck')
    expect(spell(title)).toBe('true')
    expect(title.lang).toBe('ru')
    expect(spell(email)).toBe('false')
    expect(spell(body)).toBe('true')

    act(() => setSpellcheckEnabled(false))
    expect(spell(title)).toBe('false')
    expect(spell(body)).toBe('false')
    expect(localStorage.getItem('veillou.spellcheck')).toBe('off')
  })
})
