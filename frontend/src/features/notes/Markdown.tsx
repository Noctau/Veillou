import 'katex/dist/katex.min.css'

import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'

import { cn } from '@/lib/utils'

// Ссылки из конспекта — в новой вкладке, приложение остаётся открытым
const components: Components = {
  a: ({ href, children }) => (
    <a href={href} className="text-primary underline underline-offset-4" target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
}

// Без плагина typography: стили элементов — классами Tailwind на обёртке
const PROSE = [
  'text-sm leading-relaxed break-words',
  '[&_h1]:mt-5 [&_h1]:mb-2 [&_h1]:text-xl [&_h1]:font-semibold',
  '[&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold',
  '[&_h3]:mt-3 [&_h3]:mb-1 [&_h3]:font-semibold [&_h4]:mt-3 [&_h4]:mb-1 [&_h4]:font-medium',
  '[&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-0.5',
  '[&_blockquote]:my-2 [&_blockquote]:border-l-4 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em]',
  '[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0',
  '[&_hr]:my-4 [&_img]:my-2 [&_img]:max-w-full [&_img]:rounded-lg',
  '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
  '[&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden [&_.katex-display]:py-1',
].join(' ')

/** Markdown с формулами: `$…$` в строке, `$$…$$` отдельным блоком. */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn(PROSE, className)}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false }]]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
