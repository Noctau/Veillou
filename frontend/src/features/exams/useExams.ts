import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Exam = components['schemas']['ExamRead']
export type ExamDetail = components['schemas']['ExamDetail']
export type ExamCreate = components['schemas']['ExamCreate']
export type ExamUpdate = components['schemas']['ExamUpdate']
export type ExamQuestion = components['schemas']['ExamQuestionRead']
export type ExamQuestionStatus = components['schemas']['ExamQuestionStatus']
export type ExamSession = components['schemas']['ExamSessionRead']

export function useExams(subjectId: string) {
  return useQuery({
    queryKey: queryKeys.exams(subjectId),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/exams', { params: { query: { subject_id: subjectId } } })
      if (error) throw error
      return data
    },
  })
}

export function useExam(id: string) {
  return useQuery({
    queryKey: queryKeys.exam(id),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/exams/{exam_id}', { params: { path: { exam_id: id } } })
      if (error) throw error
      return data
    },
  })
}

/** Ответ с деталями экзамена кладём в кэш; меняются и календарь, и (возможно) превью плана. */
function useOnDetail() {
  const queryClient = useQueryClient()
  return (data: ExamDetail) => {
    queryClient.setQueryData(queryKeys.exam(data.id), data)
    queryClient.invalidateQueries({ queryKey: ['exams', 'list'] })
    queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    queryClient.invalidateQueries({ queryKey: queryKeys.plan })
  }
}

export function useCreateExam() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async (body: ExamCreate) => {
      const { data, error } = await api.POST('/api/v1/exams', { body })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateExam() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: ExamUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/exams/{exam_id}', { params: { path: { exam_id: id } }, body })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useDeleteExam() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/exams/{exam_id}', { params: { path: { exam_id: id } } })
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.examsAll })
      queryClient.invalidateQueries({ queryKey: queryKeys.calendarAll })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useImportQuestions() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, text }: { id: string; text: string }) => {
      const { data, error } = await api.POST('/api/v1/exams/{exam_id}/questions/import', {
        params: { path: { exam_id: id } },
        body: { text },
      })
      if (error) throw error
      return data
    },
    onSuccess: onDetail,
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** Статус вопроса — optimistic: отметка видна сразу, план пересоберётся на сервере. */
export function useUpdateQuestion(examId: string) {
  const queryClient = useQueryClient()
  const key = queryKeys.exam(examId)
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: ExamQuestionStatus }) => {
      const { data, error } = await api.PATCH('/api/v1/exam-questions/{question_id}', {
        params: { path: { question_id: id } },
        body: { status },
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<ExamDetail>(key)
      if (prev) {
        queryClient.setQueryData<ExamDetail>(key, {
          ...prev,
          questions: prev.questions.map((q) => (q.id === id ? { ...q, status } : q)),
        })
      }
      return { prev }
    },
    onError: (error, _vars, context) => {
      if (context?.prev) queryClient.setQueryData(key, context.prev)
      toast.error(errorMessage(error))
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: ['exams', 'list'] })
    },
  })
}

export function useDeleteQuestion(examId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/exam-questions/{question_id}', {
        params: { path: { question_id: id } },
      })
      if (error) throw error
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.exam(examId) }),
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** «Построить план подготовки» → дни по билетам + превью плана в шторке. */
export function useExamPlan() {
  const onDetail = useOnDetail()
  return useMutation({
    mutationFn: async ({ id, enable }: { id: string; enable: boolean }) => {
      const params = { params: { path: { exam_id: id } } }
      const { data, error } = enable
        ? await api.POST('/api/v1/exams/{exam_id}/plan', params)
        : await api.DELETE('/api/v1/exams/{exam_id}/plan', params)
      if (error) throw error
      return data
    },
    onSuccess: (data, { enable }) => {
      onDetail(data)
      if (enable) toast.success('План подготовки готов — проверьте превью внизу и примените')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
