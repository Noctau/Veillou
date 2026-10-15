import { useSyncExternalStore } from 'react'

/*
 * Проверка правописания в полях ввода — встроенная в браузер / клавиатуру
 * (подчёркивание и варианты исправления по правому клику или тапу). Текст никуда
 * не отправляется. Русский и английский проверяются, если словари этих языков
 * включены в браузере или системе; поля помечены lang="ru" — подсказка браузеру.
 *
 * Включено по умолчанию; выключается на устройстве (вкладка «Интерфейс»).
 */

const STORAGE_KEY = 'veillou.spellcheck'
const listeners = new Set<() => void>()

function read(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'off'
  } catch {
    return true
  }
}

let enabled = read()

export function isSpellcheckEnabled(): boolean {
  return enabled
}

export function setSpellcheckEnabled(value: boolean): void {
  enabled = value
  try {
    if (value) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, 'off')
  } catch {
    // приватный режим — только до перезагрузки
  }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useSpellcheck(): boolean {
  return useSyncExternalStore(subscribe, isSpellcheckEnabled, () => true)
}

// Поля, где проверять нечего: адреса, числа, даты, пароли, файлы
const PLAIN_TYPES = new Set([undefined, 'text', 'search'])

/** Атрибуты проверки для поля: только для текста, свои значения поля — главнее. */
export function spellcheckProps(
  type: string | undefined,
  own: { spellCheck?: boolean | 'true' | 'false'; lang?: string; autoComplete?: string },
  on: boolean,
): { spellCheck: boolean; lang?: string; autoCorrect?: 'on' | 'off' } {
  const textual = PLAIN_TYPES.has(type) && !own.autoComplete?.includes('email')
  const check = own.spellCheck === undefined ? on && textual : own.spellCheck === true || own.spellCheck === 'true'
  return {
    spellCheck: check,
    lang: own.lang ?? (textual ? 'ru' : undefined),
    autoCorrect: textual ? (check ? 'on' : 'off') : undefined,
  }
}
