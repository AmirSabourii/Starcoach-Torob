// Same-origin API client for the FastAPI playground server (served at /app?token=…).
export const TOKEN = new URLSearchParams(location.search).get('token') || ''

function rid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}
export const SID = (() => {
  let s = localStorage.getItem('torob_app_sid')
  if (!s) { s = 'app_' + rid(); localStorage.setItem('torob_app_sid', s) }
  return s
})()
export const CID = (() => {
  let s = localStorage.getItem('pg_cid')
  if (!s) { s = 'c_' + rid(); localStorage.setItem('pg_cid', s) }
  return s
})()

export class ApiError extends Error {
  kind: string
  status: number
  constructor(kind: string, msg: string, status = 0) { super(msg); this.kind = kind; this.status = status }
}

export async function api<T = any>(path: string, opts: { body?: unknown; timeout?: number; retries?: number } = {}): Promise<T> {
  const { body, timeout = 15000, retries = body ? 0 : 1 } = opts
  const url = path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(TOKEN)
  let last: unknown
  for (let a = 0; a <= retries; a++) {
    const ac = new AbortController()
    const tm = window.setTimeout(() => ac.abort(), timeout)
    try {
      const r = await fetch(url, {
        method: body !== undefined ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json', 'X-Pinggy-No-Screen': 'true' },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ac.signal,
        cache: 'no-store',
      })
      const ct = r.headers.get('content-type') || ''
      if (!ct.includes('application/json')) throw new ApiError('network', 'HTTP ' + r.status, r.status)
      const j = await r.json()
      if (!r.ok) throw new ApiError(r.status === 402 ? 'cap' : r.status === 403 ? 'auth' : r.status === 404 ? 'notfound' : 'server', j.detail || j.error || 'HTTP ' + r.status, r.status)
      return j as T
    } catch (e) {
      last = e
      if (e instanceof ApiError && e.kind !== 'network') throw e
    } finally {
      window.clearTimeout(tm)
    }
  }
  if (last instanceof ApiError) throw last
  throw new ApiError('network', String((last as Error)?.message || last))
}

export function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.kind === 'auth') return 'لینک معتبر نیست؛ لینک تازه را باز کنید.'
    if (e.kind === 'cap') return 'سقف هزینهٔ این نسخهٔ آزمایشی پر شده است.'
    if (e.kind === 'notfound') return 'پیدا نشد.'
    if (e.kind === 'network') return 'ارتباط برقرار نشد؛ شاید لینک عوض شده باشد. دوباره امتحان کنید.'
    return 'مشکلی پیش آمد. دوباره امتحان کنید.'
  }
  return 'ارتباط برقرار نشد؛ دوباره امتحان کنید.'
}

export type StreamEv = { event: string; data: any }
/** POST /api/send_stream (SSE). Resolves with the `final` payload. Throws ApiError('nostream') if the stream could not start,
 *  so the caller may fall back to /api/send without double-sending; errors after the first event are thrown as 'server'. */
export async function sendStream(body: unknown, onEv: (e: StreamEv) => void, timeout = 150000): Promise<any> {
  const url = '/api/send_stream?token=' + encodeURIComponent(TOKEN)
  const ac = new AbortController()
  const tm = window.setTimeout(() => ac.abort(), timeout)
  let started = false
  try {
    let r: Response
    try {
      r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Pinggy-No-Screen': 'true', Accept: 'text/event-stream' }, body: JSON.stringify(body), signal: ac.signal, cache: 'no-store' })
    } catch (e) { throw new ApiError('nostream', String((e as Error)?.message || e)) }
    const ct = r.headers.get('content-type') || ''
    if (!r.ok || !ct.includes('text/event-stream') || !r.body) {
      if (r.status === 402) throw new ApiError('cap', 'cap', 402)
      if (r.status === 403) throw new ApiError('auth', 'auth', 403)
      throw new ApiError('nostream', 'HTTP ' + r.status, r.status)
    }
    const rd = r.body.getReader()
    const dec = new TextDecoder()
    let buf = '', final: any = null
    for (;;) {
      const { value, done } = await rd.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let k
      while ((k = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, k); buf = buf.slice(k + 2)
        let ev = 'message', data = ''
        for (const line of raw.split('\n')) {
          if (line.startsWith('event:')) ev = line.slice(6).trim()
          else if (line.startsWith('data:')) data += line.slice(5).trim()
        }
        let d: any = null
        try { d = data ? JSON.parse(data) : null } catch { continue }
        started = true
        if (ev === 'error') throw new ApiError(d?.error && /سقف/.test(d.error) ? 'cap' : 'server', d?.error || 'stream error')
        if (ev === 'final') final = d
        else onEv({ event: ev, data: d })
      }
    }
    if (!final) throw new ApiError(started ? 'server' : 'nostream', 'stream ended without final')
    return final
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError(started ? 'server' : 'nostream', String((e as Error)?.message || e))
  } finally { window.clearTimeout(tm) }
}
