import { describe, expect, it } from 'vitest'

import { fromSteps, moveStep, removeStep, timeWarning, toSteps, totalMinutes, validStep } from './draft'

const STEPS = [
  { title: 'Найти источники', estimate_min: 40, depends_on: [], note: '' },
  { title: 'Написать', estimate_min: 90, depends_on: [0], note: '' },
  { title: 'Сдать', estimate_min: 15, depends_on: [0, 1], note: '' },
]

describe('черновик разбивки', () => {
  it('туда и обратно сохраняет зависимости', () => {
    const draft = fromSteps(STEPS)
    expect(toSteps(draft).map((s) => s.depends_on)).toEqual([[], [0], [0, 1]])
    expect(totalMinutes(draft)).toBe(145)
  })

  it('перетаскивание вверх снимает зависимости от шагов, оказавшихся ниже', () => {
    const moved = moveStep(fromSteps(STEPS), 2, 0)
    expect(moved[0].title).toBe('Сдать')
    expect(moved[0].depends_on).toEqual([])
    expect(toSteps(moved).map((s) => s.depends_on)).toEqual([[], [], [1]])
  })

  it('удаление шага убирает ссылки на него', () => {
    const draft = fromSteps(STEPS)
    const left = removeStep(draft, draft[0].key)
    expect(toSteps(left).map((s) => s.depends_on)).toEqual([[], [0]])
  })

  it('валидация шага', () => {
    const [step] = fromSteps(STEPS)
    expect(validStep(step)).toBe(true)
    expect(validStep({ ...step, title: '  ' })).toBe(false)
    expect(validStep({ ...step, estimate_min: 4 })).toBe(false)
    expect(validStep({ ...step, estimate_min: 30.5 })).toBe(false)
  })

  it('предупреждение о времени — как на сервере', () => {
    expect(timeWarning(100, null, 1)).toBeNull()
    expect(timeWarning(100, 0, 1)).toBe('До дедлайна свободного времени не осталось')
    expect(timeWarning(100, 60, 1)).toMatch(/^Нужно ~/)
    expect(timeWarning(100, 110, 1)).toMatch(/^Впритык/)
    expect(timeWarning(100, 500, 1)).toBeNull()
  })
})
