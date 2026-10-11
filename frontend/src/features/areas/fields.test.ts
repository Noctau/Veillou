import { describe, expect, it } from 'vitest'

import { compactValues, renderFields } from './fields'
import type { FieldDef } from './useAreas'

const def = (over: Partial<FieldDef> & Pick<FieldDef, 'id' | 'type'>): FieldDef => ({
  label: over.id,
  options: [],
  multiple: false,
  show_in_reminder: false,
  required: false,
  ...over,
})

describe('renderFields', () => {
  it('как domain/fields.render_values: порядок полей, форматы, пустые пропускаются', () => {
    const defs = [
      def({ id: 'grade', label: 'Класс', type: 'text' }),
      def({ id: 'rate', label: 'Ставка', type: 'number', show_in_reminder: true }),
      def({ id: 'paid', label: 'Оплачено', type: 'bool' }),
      def({ id: 'since', label: 'С', type: 'date' }),
      def({ id: 'people', label: 'Преподаватели', type: 'contact', multiple: true }),
      def({ id: 'links', label: 'Ссылки', type: 'link', multiple: true }),
      def({ id: 'empty', label: 'Пусто', type: 'text' }),
    ]
    const values = {
      links: [{ title: '', url: 'https://x.ru/a' }, { title: 'Курс', url: 'https://y.ru' }],
      people: [{ name: 'Иванов', role: 'лектор', phone: '+7 900' }, { role: 'семинарист' }],
      since: '2026-09-01',
      paid: false,
      rate: 1.5,
      grade: '9Б',
      empty: '',
    }
    expect(renderFields(defs, values).map((r) => [r.def.label, r.text])).toEqual([
      ['Класс', '9Б'],
      ['Ставка', '1,5'],
      ['Оплачено', 'нет'],
      ['С', '01.09.2026'],
      ['Преподаватели', 'Иванов (лектор) · +7 900; семинарист'],
      ['Ссылки', 'x.ru, Курс'],
    ])
    expect(renderFields(defs, values, { onlyReminder: true }).map((r) => r.text)).toEqual(['1,5'])
  })

  it('сфера — по названию, неизвестная пропускается', () => {
    const defs = [def({ id: 'subj', label: 'Предмет', type: 'area_ref' })]
    expect(renderFields(defs, { subj: 'a1' })).toEqual([])
    expect(renderFields(defs, { subj: 'a1' }, { areaNames: { a1: 'Алгебра' } })[0].text).toBe('Алгебра')
  })

  it('пустые значения формы не отправляются', () => {
    expect(compactValues({ a: '', b: [], c: {}, d: null, e: false, f: 0, g: 'x' })).toEqual({ e: false, f: 0, g: 'x' })
  })
})
