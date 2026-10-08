import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { FEEL_LABEL } from '@/features/tasks/labels'
import type { Feel } from '@/features/tasks/useTasks'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

const FEELS: Feel[] = ['faster', 'ok', 'slower']

/**
 * После «сделано» на блоке подзадачи — необязательный вопрос «как по времени?»
 * (калибровка оценок, M9.4). Тост сам исчезает, если не ответить.
 */
export function useAskFeel() {
  const queryClient = useQueryClient()

  const pick = async (toastId: string | number, subtaskId: string, feel: Feel) => {
    toast.dismiss(toastId)
    const { error } = await api.PATCH('/api/v1/subtasks/{subtask_id}', {
      params: { path: { subtask_id: subtaskId } },
      body: { actual_feel: feel },
    })
    if (error) toast.error(errorMessage(error))
    queryClient.invalidateQueries({ queryKey: queryKeys.tasks })
    queryClient.invalidateQueries({ queryKey: queryKeys.calibration })
  }

  return (subtaskId: string) =>
    toast.custom(
      (id) => (
        <div className="flex w-[var(--width)] flex-col gap-2 rounded-lg border bg-popover p-3 text-sm text-popover-foreground shadow-lg">
          <span>Сделано! Как по времени?</span>
          <div className="flex gap-1">
            {FEELS.map((f) => (
              <Button key={f} size="sm" variant="outline" className="flex-1" onClick={() => void pick(id, subtaskId, f)}>
                {FEEL_LABEL[f]}
              </Button>
            ))}
          </div>
        </div>
      ),
      { duration: 8000 },
    )
}
