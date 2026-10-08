import { AlertTriangleIcon } from 'lucide-react'
import { useLayoutEffect, useRef } from 'react'

import { useTimeZone } from '@/features/schedule/useCurrentSemester'
import { formatDay, todayIn } from '@/lib/time'
import { cn } from '@/lib/utils'

import { buildTimeline, shortTitle, type TimelinePoint } from './timeline'
import type { ProjectDetail } from './useProjects'

const H = 116
const AXIS = 74
const LABEL_Y = [58, 44, 30] as const

const DOT: Record<TimelinePoint['state'], string> = {
  done: 'fill-emerald-500 stroke-emerald-500',
  late: 'fill-destructive stroke-destructive',
  planned: 'fill-background stroke-primary',
}

/**
 * Таймлайн проекта (M13.3): этапы на шкале месяцев, отметка «сегодня»,
 * итоговый срок. Просроченные этапы и отрезок отставания — красным.
 */
export function ProjectTimeline({ project }: { project: ProjectDetail }) {
  const tz = useTimeZone()
  const today = todayIn(tz)
  const scroller = useRef<HTMLDivElement>(null)
  const t = buildTimeline(project.milestones, project.deadline, today)

  // Сегодня — посередине видимой части
  useLayoutEffect(() => {
    const el = scroller.current
    if (el) el.scrollLeft = Math.max(0, t.todayX - el.clientWidth / 2)
  }, [t.todayX])

  if (!t.points.length && t.deadlineX === null) return null
  const clamp = (x: number) => Math.min(Math.max(x, 36), t.width - 36)
  const late = t.points.filter((p) => p.state === 'late')

  return (
    <div className="flex flex-col gap-2">
      {project.behind_days > 0 && (
        <p className="flex items-center gap-1.5 text-sm text-destructive">
          <AlertTriangleIcon className="size-4 shrink-0" />
          Отставание {project.behind_days} дн.:{' '}
          {late.length > 1 ? `просрочено этапов — ${late.length}` : `«${late[0]?.milestone.title}»`}
        </p>
      )}
      <div ref={scroller} className="overflow-x-auto pb-1">
        <svg width={t.width} height={H} role="img" aria-label="Таймлайн проекта" className="block">
          {/* Шкала: пройденное — темнее */}
          <line
            x1={0}
            x2={t.width}
            y1={AXIS}
            y2={AXIS}
            className="stroke-border"
            strokeWidth={4}
            strokeLinecap="round"
          />
          <line
            x1={0}
            x2={t.todayX}
            y1={AXIS}
            y2={AXIS}
            className="stroke-muted-foreground/50"
            strokeWidth={4}
            strokeLinecap="round"
          />
          {t.lag && (
            <line
              x1={t.lag.from}
              x2={t.lag.to}
              y1={AXIS}
              y2={AXIS}
              className="stroke-destructive/60"
              strokeWidth={4}
              strokeLinecap="round"
            />
          )}

          {t.months.map((m) => (
            <g key={m.x}>
              <line x1={m.x} x2={m.x} y1={AXIS + 4} y2={AXIS + 9} className="stroke-muted-foreground/60" />
              <text x={m.x + 4} y={AXIS + 20} className="fill-muted-foreground text-[10px]">
                {m.label}
              </text>
              {m.year && (
                <text x={m.x + 4} y={AXIS + 33} className="fill-muted-foreground text-[10px]">
                  {m.year}
                </text>
              )}
            </g>
          ))}

          {/* Сегодня */}
          <line x1={t.todayX} x2={t.todayX} y1={16} y2={AXIS + 8} className="stroke-primary" strokeDasharray="3 3" />
          <text x={clamp(t.todayX)} y={12} textAnchor="middle" className="fill-primary text-[10px] font-medium">
            сегодня
          </text>

          {/* Итоговый срок */}
          {t.deadlineX !== null && (
            <g>
              <title>Итоговый срок: {formatDay(project.deadline!, { year: 'numeric' })}</title>
              <rect
                x={t.deadlineX - 6}
                y={AXIS - 6}
                width={12}
                height={12}
                transform={`rotate(45 ${t.deadlineX} ${AXIS})`}
                className="fill-foreground"
              />
            </g>
          )}

          {t.points.map((p) => (
            <g key={p.milestone.id}>
              <title>
                {p.milestone.title} — {formatDay(p.milestone.date!, { year: 'numeric' })}
                {p.state === 'done' ? ' (выполнен)' : p.state === 'late' ? ' (просрочен)' : ''}
              </title>
              <line x1={p.x} x2={p.x} y1={LABEL_Y[p.row] + 4} y2={AXIS - 6} className="stroke-muted-foreground/40" />
              <circle cx={p.x} cy={AXIS} r={6} strokeWidth={2} className={DOT[p.state]} />
              <text
                x={clamp(p.x)}
                y={LABEL_Y[p.row]}
                textAnchor="middle"
                className={cn(
                  'text-[10px]',
                  p.state === 'late'
                    ? 'fill-destructive'
                    : p.state === 'done'
                      ? 'fill-muted-foreground'
                      : 'fill-foreground',
                )}
              >
                {shortTitle(p.milestone.title)}
              </text>
            </g>
          ))}
        </svg>
      </div>
      {t.undated > 0 && <p className="text-xs text-muted-foreground">Без даты — {t.undated}: на шкале их нет.</p>}
    </div>
  )
}
