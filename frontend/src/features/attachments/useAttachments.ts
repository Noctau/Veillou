import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { components } from '@/api/schema'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { queryKeys } from '@/lib/queryKeys'

export type Attachment = components['schemas']['AttachmentRead']
export type AttachmentOwner = components['schemas']['AttachmentOwner']

// Ссылки на файлы подписаны на час — обновляем список заранее
const URL_REFRESH_MS = 30 * 60_000

export function useAttachments(ownerType: AttachmentOwner, ownerId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.attachments(ownerType, ownerId ?? ''),
    enabled: !!ownerId,
    staleTime: URL_REFRESH_MS,
    refetchInterval: URL_REFRESH_MS,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/attachments', {
        params: { query: { owner_type: ownerType, owner_id: ownerId! } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useUploadAttachment(ownerType: AttachmentOwner, ownerId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
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
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.attachments(ownerType, ownerId) }),
    onError: (error) => toast.error(errorMessage(error, 'Не удалось загрузить файл')),
  })
}

export function useDeleteAttachment(ownerType: AttachmentOwner, ownerId: string) {
  const queryClient = useQueryClient()
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
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  })
}
