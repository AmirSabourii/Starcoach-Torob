// Try-on API client (POST /api/tryon, GET /api/tryon/eligibility/:pid). Self-contained; reuses the app's TOKEN/SID.
import { SID, TOKEN } from '../api'

export type TryOnMode = 'room' | 'person'
export type Eligibility = {
  ok: boolean; eligible: boolean; product_id: string; category?: string; title?: string; image?: string | null; min_price?: number | null
  mode?: TryOnMode; kind?: 'home' | 'fashion'; noun?: string; cta?: string; busy_text?: string; ask?: string; remaining?: number; per_session?: number
}
export type TryOnResult = {
  ok: true; status: 'done'; product_id: string; mode: TryOnMode; noun: string; key: string; cached: boolean; cost_usd: number
  model: string; elapsed_s: number; width?: number; height?: number; image_url: string; remaining: number; caption: string
}
export class TryOnError extends Error {
  code: string; status: number
  constructor(code: string, msg: string, status = 0) { super(msg); this.code = code; this.status = status }
}

const MAX_BYTES = 8 * 1024 * 1024
const MAX_SIDE = 1024
const q = (p: string) => p + (p.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(TOKEN)

export async function fetchEligibility(pid: string, signal?: AbortSignal): Promise<Eligibility> {
  const r = await fetch(q(`/api/tryon/eligibility/${encodeURIComponent(pid)}?sid=${encodeURIComponent(SID)}`), { signal, headers: { 'X-Pinggy-No-Screen': 'true' }, cache: 'no-store' })
  const j = await r.json().catch(() => null)
  if (!r.ok || !j) throw new TryOnError(j?.code || 'network', j?.error || 'ارتباط برقرار نشد.', r.status)
  return j as Eligibility
}

/** validates (≤ 8MB, image/*) and downsizes to ≤ 1024px JPEG in the browser; returns the blob to upload + an object URL for «قبل» */
export async function preparePhoto(file: File): Promise<{ blob: Blob; url: string }> {
  if (!file.type.startsWith('image/') && !/\.(jpe?g|png|webp|heic|heif)$/i.test(file.name)) throw new TryOnError('not_image', 'فایل انتخاب‌شده عکس نیست.')
  if (file.size > MAX_BYTES) throw new TryOnError('too_large', 'حجم عکس بیشتر از ۸ مگابایت است؛ عکس کوچک‌تری انتخاب کن.')
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' } as ImageBitmapOptions)
    const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height))
    const w = Math.round(bmp.width * k), h = Math.round(bmp.height * k)
    const c = document.createElement('canvas'); c.width = w; c.height = h
    c.getContext('2d')!.drawImage(bmp, 0, 0, w, h)
    bmp.close?.()
    const blob = await new Promise<Blob | null>((res) => c.toBlob(res, 'image/jpeg', 0.9))
    if (blob) return { blob, url: URL.createObjectURL(blob) }
  } catch { /* e.g. HEIC the browser can't decode: send the original, the server validates/resizes */ }
  return { blob: file, url: URL.createObjectURL(file) }
}

export async function runTryOn(pid: string, mode: TryOnMode, photo: Blob, signal?: AbortSignal, timeoutMs = 100000): Promise<TryOnResult> {
  const fd = new FormData()
  fd.append('product_id', pid); fd.append('mode', mode); fd.append('sid', SID); fd.append('photo', photo, 'photo.jpg')
  const ac = new AbortController()
  const tm = window.setTimeout(() => ac.abort('timeout'), timeoutMs)
  const onAbort = () => ac.abort('cancel')
  signal?.addEventListener('abort', onAbort)
  try {
    const r = await fetch(q('/api/tryon'), { method: 'POST', body: fd, signal: ac.signal, headers: { 'X-Pinggy-No-Screen': 'true' } })
    const j = await r.json().catch(() => null)
    if (!r.ok || !j?.ok) throw new TryOnError(j?.code || 'server', j?.error || 'مشکلی پیش آمد؛ دوباره امتحان کن.', r.status)
    return { ...j, image_url: j.image_url.includes('token=') ? j.image_url : q(j.image_url) } as TryOnResult
  } catch (e) {
    if (e instanceof TryOnError) throw e
    if (ac.signal.aborted) throw ac.signal.reason === 'cancel' ? new TryOnError('cancelled', 'لغو شد.') : new TryOnError('timeout', 'ساخت تصویر بیش از حد طول کشید؛ دوباره امتحان کن.')
    throw new TryOnError('network', 'ارتباط برقرار نشد؛ دوباره امتحان کن.')
  } finally {
    window.clearTimeout(tm); signal?.removeEventListener('abort', onAbort)
  }
}
