import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Attachment = components['schemas']['AttachmentRead']
export type AttachmentOwner = components['schemas']['AttachmentOwner']

// Ссылки на файлы подписаны на час — обновляем список заранее
const URL_REFRESH_MS = 30 * 60_000

export function attachmentsQueryOptions(ownerType: AttachmentOwner, ownerId: string) {
  return queryOptions({
    queryKey: queryKeys.attachments(ownerType, ownerId),
    staleTime: URL_REFRESH_MS,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/attachments', {
        params: { query: { owner_type: ownerType, owner_id: ownerId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useAttachments(ownerType: AttachmentOwner, ownerId: string | undefined) {
  return useQuery({
    ...attachmentsQueryOptions(ownerType, ownerId ?? ''),
    enabled: !!ownerId,
    refetchInterval: URL_REFRESH_MS,
  })
}

/** Список файлов и всё, что показывает их сводку (обложка и число страниц конспекта). */
function useInvalidateOwner(ownerType: AttachmentOwner, ownerId: string) {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.attachments(ownerType, ownerId) })
    if (ownerType === 'note') queryClient.invalidateQueries({ queryKey: queryKeys.notesAll })
  }
}

/** Загрузка файла без хука — когда владелец создаётся тут же (быстрое добавление из «Поделиться»). */
export async function uploadAttachment(ownerType: AttachmentOwner, ownerId: string, file: File): Promise<Attachment> {
  const form = new FormData()
  form.append('owner_type', ownerType)
  form.append('owner_id', ownerId)
  form.append('file', file)
  const { data, error } = await api.POST('/api/v1/attachments', {
    // Тело — multipart; типы openapi-fetch описывают его полями, отдаём FormData как есть
    body: { owner_type: ownerType, owner_id: ownerId, file: '' },
    bodySerializer: () => form,
  })
  if (error) throw error
  return data
}

export function useUploadAttachment(ownerType: AttachmentOwner, ownerId: string) {
  const invalidate = useInvalidateOwner(ownerType, ownerId)
  return useMutation({
    mutationFn: (file: File) => uploadAttachment(ownerType, ownerId, file),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error, 'Не удалось загрузить файл')),
  })
}

/** Новое содержимое того же файла (повёрнутая страница). */
export function useReplaceAttachment(ownerType: AttachmentOwner, ownerId: string) {
  const invalidate = useInvalidateOwner(ownerType, ownerId)
  return useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      const { data, error } = await api.POST('/api/v1/attachments/{attachment_id}/replace', {
        params: { path: { attachment_id: id } },
        body: { file: '' },
        bodySerializer: () => form,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error, 'Не удалось сохранить страницу')),
  })
}

export function useReorderAttachments(ownerType: AttachmentOwner, ownerId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateOwner(ownerType, ownerId)
  const key = queryKeys.attachments(ownerType, ownerId)
  return useMutation({
    mutationFn: async (ids: string[]) => {
      const { data, error } = await api.PUT('/api/v1/attachments/order', {
        body: { owner_type: ownerType, owner_id: ownerId, ids },
      })
      if (error) throw error
      return data
    },
    onMutate: async (ids) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<Attachment[]>(key)
      if (prev) {
        const byId = new Map(prev.map((a) => [a.id, a]))
        const moved = ids.flatMap((id, position) => (byId.has(id) ? [{ ...byId.get(id)!, position }] : []))
        // Файлы, которых нет в ids (другой тип в том же объекте), остаются в конце
        const rest = prev.filter((a) => !ids.includes(a.id))
        queryClient.setQueryData<Attachment[]>(key, [...moved, ...rest])
      }
      return { prev }
    },
    onError: (error, _ids, context) => {
      queryClient.setQueryData(key, context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}

export function useDeleteAttachment(ownerType: AttachmentOwner, ownerId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateOwner(ownerType, ownerId)
  const key = queryKeys.attachments(ownerType, ownerId)
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/v1/attachments/{attachment_id}', {
        params: { path: { attachment_id: id } },
      })
      if (error) throw error
    },
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: key })
      const prev = queryClient.getQueryData<Attachment[]>(key)
      queryClient.setQueryData<Attachment[]>(key, (old) => old?.filter((a) => a.id !== id))
      return { prev }
    },
    onError: (error, _id, context) => {
      queryClient.setQueryData(key, context?.prev)
      toast.error(errorMessage(error))
    },
    onSettled: invalidate,
  })
}
