/**
 * Фото страниц на клиенте: сжатие перед загрузкой и поворот. Только canvas,
 * без библиотек. Ориентацию из EXIF браузер применяет сам (createImageBitmap).
 */

const MAX_SIDE = 2200 // хватает, чтобы читать формулы с тетрадного листа
const QUALITY = 0.82

async function toBitmap(blob: Blob): Promise<ImageBitmap> {
  return createImageBitmap(blob, { imageOrientation: 'from-image' })
}

function canvasToFile(canvas: HTMLCanvasElement, name: string): Promise<File> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(new File([blob], name, { type: 'image/jpeg' })) : reject(new Error('Не удалось сжать фото'))),
      'image/jpeg',
      QUALITY,
    ),
  )
}

function jpegName(name: string): string {
  return `${name.replace(/\.[^.]+$/, '') || 'страница'}.jpg`
}

/** Уменьшает фото до MAX_SIDE по длинной стороне и пережимает в JPEG.
 *  Если браузер не умеет формат (HEIC на ноутбуке) — отдаёт файл как есть. */
export async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.type === 'image/gif') return file
  let bitmap: ImageBitmap
  try {
    bitmap = await toBitmap(file)
  } catch {
    return file
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  const compressed = await canvasToFile(canvas, jpegName(file.name))
  // Маленький уже сжатый JPEG мог стать больше — оставляем оригинал
  return compressed.size < file.size ? compressed : file
}

/** Поворот картинки на ±90° (по часовой — положительный). */
export async function rotateImage(blob: Blob, name: string, degrees: 90 | -90): Promise<File> {
  const bitmap = await toBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.height
  canvas.height = bitmap.width
  const ctx = canvas.getContext('2d')!
  ctx.translate(canvas.width / 2, canvas.height / 2)
  ctx.rotate((degrees * Math.PI) / 180)
  ctx.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2)
  bitmap.close()
  return canvasToFile(canvas, jpegName(name))
}
