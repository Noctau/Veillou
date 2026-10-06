import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components, operations } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Note = components['schemas']['NoteRead']
export type NoteListItem = components['schemas']['NoteListItem']
export type NoteCreate = components['schemas']['NoteCreate']
export type NoteUpdate = components['schemas']['NoteUpdate']
export type NoteKind = components['schemas']['NoteKind']
export type NoteListParams = NonNullable<operations['list_notes']['parameters']['query']>

// В списке есть подписанные ссылки на обложки — живут час
const URL_REFRESH_MS = 30 * 60_000

export function notesQueryOptions(params: NoteListParams = {}) {
  return queryOptions({
    queryKey: queryKeys.noteList(params),
    staleTime: URL_REFRESH_MS,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/notes', { params: { query: params } })
      if (error) throw error
      return data
    },
  })
}

export function noteQueryOptions(id: string) {
  return queryOptions({
    queryKey: queryKeys.note(id),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/notes/{note_id}', {
        params: { path: { note_id: id } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useNotes(params: NoteListParams = {}, enabled = true) {
  return useQuery({ ...notesQueryOptions(params), enabled })
}

export function useNote(id: string | undefined) {
  return useQuery({ ...noteQueryOptions(id ?? ''), enabled: !!id })
}

export function useCreateNote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: NoteCreate) => {
      const { data, error } = await api.POST('/api/v1/notes', { body })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.note(data.id), data)
      queryClient.invalidateQueries({ queryKey: queryKeys.notesList })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

export function useUpdateNote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: NoteUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/notes/{note_id}', {
        params: { path: { note_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onMutate: async ({ id, body }) => {
      const key = queryKeys.note(id)
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<Note>(key)
      if (prev) queryClient.setQueryData<Note>(key, { ...prev, ...(body as Partial<Note>) })
      return { prev }
    },
    onSuccess: (data) => queryClient.setQueryData(queryKeys.note(data.id), data),
    onError: (error, { id }, context) => {
      if (context?.prev) queryClient.setQueryData(queryKeys.note(id), context.prev)
      toast.error(errorMessage(error, 'Не удалось сохранить конспект'))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.notesList }),
  })
}

export function useDeleteNote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/notes/{note_id}', {
        params: { path: { note_id: id } },
      })
      if (error) throw error
    },
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: queryKeys.note(id) })
      queryClient.invalidateQueries({ queryKey: queryKeys.notesList })
      toast.success('Конспект удалён')
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}

/** «Конспект к этой паре»: открыть начатый конспект пары или создать новый. */
export function useNoteForEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ eventId, kind = 'text' }: { eventId: string; kind?: NoteKind }) => {
      const { data, error } = await api.POST('/api/v1/notes/for-event/{event_id}', {
        params: { path: { event_id: eventId }, query: { kind } },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.note(data.id), data)
      queryClient.invalidateQueries({ queryKey: queryKeys.notesList })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
