import type { components } from '@/api/schema'

type ErrorResponse = components['schemas']['ErrorResponse']
type HTTPValidationError = components['schemas']['HTTPValidationError']

function isErrorResponse(e: object): e is ErrorResponse {
  return 'error' in e && typeof (e as ErrorResponse).error?.message === 'string'
}

function isValidationError(e: object): e is HTTPValidationError {
  return 'detail' in e && Array.isArray((e as HTTPValidationError).detail)
}

/** Человекочитаемый текст ошибки API или сети. */
export function errorMessage(error: unknown, fallback = 'Что-то пошло не так'): string {
  if (error instanceof TypeError) return 'Нет связи с сервером'
  if (error && typeof error === 'object') {
    if (isErrorResponse(error)) return error.error.message
    if (isValidationError(error) && error.detail?.length) return error.detail[0].msg
  }
  if (error instanceof Error) return error.message
  return fallback
}

/** Машинный код ошибки API (`plan_stale`, `not_found`…), если есть. */
export function errorCode(error: unknown): string | undefined {
  return error && typeof error === 'object' && isErrorResponse(error) ? error.error.code : undefined
}
