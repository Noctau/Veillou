import { describe, expect, it } from 'vitest'

import { buildNav, fixedNav } from './nav'

const STUDENTS = { id: '11111111-1111-1111-1111-111111111111', name_plural: 'Ученики', icon: 'users' as const }
const SUBJECTS = { id: '22222222-2222-2222-2222-222222222222', name_plural: 'Предметы', icon: 'graduation-cap' as const }
const MASHA = { id: '33333333-3333-3333-3333-333333333333', name: 'Маша Петрова', short_name: 'Маша', area_type_id: STUDENTS.id }

describe('buildNav (M22.2)', () => {
  it('закреплены «Сегодня», «Календарь», ＋', () => {
    expect(fixedNav.map((i) => i.to)).toEqual(['/', '/calendar', '/add'])
    expect(fixedNav[2].primary).toBe(true)
  })

  it('студентка: как в Part 1 — «Сферы» и «Ящик»', () => {
    const nav = buildNav(['areas', 'inbox'], [SUBJECTS])
    expect(nav.map((i) => [i.to, i.label])).toEqual([
      ['/areas', 'Сферы'],
      ['/inbox', 'Ящик'],
    ])
  })

  it('репетитор: «Ученики» вместо «Сфер», конкретная ученица, свои разделы', () => {
    const nav = buildNav(
      [`area_type:${STUDENTS.id}`, `area:${MASHA.id}`, 'projects', 'notes', 'tasks'],
      [STUDENTS, SUBJECTS],
      [MASHA],
    )
    expect(nav.map((i) => [i.to, i.label])).toEqual([
      [`/areas?type=${STUDENTS.id}`, 'Ученики'],
      [`/areas/${MASHA.id}`, 'Маша'],
      ['/projects', 'Проекты'],
      ['/notes', 'Заметки'],
      ['/tasks', 'Задачи'],
    ])
  })

  it('удалённые сферы и типы пропускаются', () => {
    const gone = '44444444-4444-4444-4444-444444444444'
    expect(buildNav([`area_type:${gone}`, `area:${gone}`, 'inbox'], [STUDENTS], [MASHA]).map((i) => i.to)).toEqual([
      '/inbox',
    ])
  })
})
