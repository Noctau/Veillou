import { useState } from 'react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { formatMinutes } from '@/features/tasks/labels'

import { type ProjectDetail, useUpdateProject } from './useProjects'

const MAX_HOURS = 60

/**
 * Недельная норма проекта (M13.1): план резервирует её блоками «работа над
 * проектом»; шаги заданий проекта засчитываются в норму.
 */
export function WeeklyNorm({ project }: { project: ProjectDetail }) {
  const update = useUpdateProject()
  const norm = project.weekly_norm_min ?? 0
  const [hours, setHours] = useState(norm ? String(norm / 60) : '')

  const save = () => {
    const value = hours.trim() ? Math.round(Number(hours) * 60) : 0
    if (!(value >= 0 && value <= MAX_HOURS * 60)) {
      setHours(norm ? String(norm / 60) : '')
      return
    }
    if (value !== norm)
      update.mutate({
        id: project.id,
        body: { weekly_norm_min: value || null },
      })
  }

  const planned = Math.min(project.week_planned_min, norm)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <Label htmlFor="project-norm" className="flex-1">
          Часов в неделю
        </Label>
        <Input
          id="project-norm"
          type="number"
          inputMode="decimal"
          min={0}
          max={MAX_HOURS}
          step={0.5}
          placeholder="—"
          className="w-24"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        />
      </div>
      {norm > 0 ? (
        <>
          <Progress
            value={Math.min(100, (project.week_done_min / norm) * 100)}
            className="h-2"
            aria-label="Сделано за неделю"
          />
          <p className="text-sm text-muted-foreground">
            На этой неделе: сделано {formatMinutes(project.week_done_min)} из {formatMinutes(norm)}
            {project.week_planned_min > project.week_done_min &&
              ` · в плане ещё ${formatMinutes(project.week_planned_min - project.week_done_min)}`}
            {planned < norm && project.week_planned_min > 0 && ` · не хватает ${formatMinutes(norm - planned)}`}
          </p>
          <p className="text-xs text-muted-foreground">
            План резервирует это время блоками «работа над проектом» на эту и следующую неделю. Шаги заданий проекта
            засчитываются в норму.
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Задайте норму — план сам найдёт время на проект, даже когда близких сроков нет.
        </p>
      )}
    </div>
  )
}
