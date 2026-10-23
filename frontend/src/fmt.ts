const FA = '۰۱۲۳۴۵۶۷۸۹'
export const fa = (v: number | string | null | undefined) => (v === null || v === undefined ? '' : String(v).replace(/\d/g, (d) => FA[+d]))
/** 1234567 -> «۱٬۲۳۴٬۵۶۷» (Persian digits, Persian thousands separator) */
export const faNum = (n: number | null | undefined) =>
  n === null || n === undefined ? '' : fa(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '٬'))
export const UNKNOWN = 'نامشخص'
export const toman = (n: number | null | undefined) => (n === null || n === undefined ? UNKNOWN : faNum(n) + ' تومان')
export const short = (t: string | null | undefined, n = 60) => {
  const s = (t || '').replace(/\s+/g, ' ').trim()
  return s.length <= n ? s : s.slice(0, n).replace(/\s+\S*$/, '') + '…'
}
export const clean = (t: string | null | undefined) => (t || '').replace(/\s+/g, ' ').trim()
export const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, '') } catch { return u } }
/** strips the server's provenance parenthesis «(ساعت ثبت‌شده؛ …)» — no disclaimer lines in the UI */
export const stripParen = (t: string | null | undefined) => (t || '').replace(/\s*\([^)]*\)\s*/g, ' ').trim()
/** «هدفون بلوتوثی انکر Soundcore R50i مدل A3949» -> ['هدفون بلوتوثی انکر', 'Soundcore R50i'] */
export const splitTitle = (t: string | null | undefined): [string, string] => {
  const s = clean(t)
  const i = s.search(/[A-Za-z]/)
  if (i <= 0) return [s, '']
  const faPart = s.slice(0, i).replace(/\s*(مدل|-|–)\s*$/, '').trim()
  const rest = s.slice(i)
  const j = rest.search(/[\u0600-\u06FF]/)
  const latin = (j > 0 ? rest.slice(0, j) : rest).replace(/[\s\-–(]+$/, '').trim()
  return [faPart || s, latin]
}
/** 151000000 -> «۱۵۱» ; 1390000 -> «۱٫۴» (millions) */
export const milNum = (n: number) => {
  const m = n / 1e6
  const v = m >= 100 ? Math.round(m).toString() : m >= 10 ? (Math.round(m * 10) / 10).toString() : (Math.round(m * 10) / 10).toString()
  return fa(v.replace('.', '٫'))
}
export const milRange = (a: number | null | undefined, b: number | null | undefined) => {
  if (!a) return UNKNOWN
  if (a < 1e6) return b && b !== a ? `${faNum(a)} تا ${faNum(b)} تومان` : `${faNum(a)} تومان`
  if (!b || milNum(a) === milNum(b)) return `${milNum(a)} میلیون تومان`
  return `${milNum(a)} تا ${milNum(b)} میلیون تومان`
}
