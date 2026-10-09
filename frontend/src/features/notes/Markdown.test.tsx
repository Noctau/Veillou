import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('рендерит формулы KaTeX (rehype-katex на katex из overrides)', () => {
    const { container } = render(<Markdown>{'Закон: $p = \\rho R T$\n\n$$\n\\int_0^1 x\\,dx\n$$'}</Markdown>)
    expect(container.querySelectorAll('.katex').length).toBe(2)
    expect(container.querySelector('.katex-display')).not.toBeNull()
  })

  it('не вставляет сырой HTML и javascript:-ссылки', () => {
    const { container } = render(
      <Markdown>{'<img src=x onerror=alert(1)> [клик](javascript:alert(1)) [ок](https://x.ru)'}</Markdown>,
    )
    expect(container.querySelector('img')).toBeNull()
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['', 'https://x.ru'])
  })
})
