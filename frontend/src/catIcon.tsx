// Shop main category -> line icon + pastel tile. Icon by keyword, colour by a stable hash of the category name (same category = same look).
import type { CSSProperties } from 'react'

const P = (d: string) => <path d={d} />
const ICONS: Record<string, JSX.Element> = {
  game: <>{P('M7.5 8h9a4.5 4.5 0 0 1 4.4 5.4l-.6 3a2.4 2.4 0 0 1-4.2 1L14.6 16H9.4l-1.5 1.4a2.4 2.4 0 0 1-4.2-1l-.6-3A4.5 4.5 0 0 1 7.5 8Z')}{P('M7.5 11v3M6 12.5h3')}<circle cx="15.5" cy="11.6" r=".6" /><circle cx="17" cy="13.4" r=".6" /></>,
  phone: <><rect x="7" y="3" width="10" height="18" rx="2.6" />{P('M11 17.6h2')}</>,
  headphone: <>{P('M4.5 15v-2.5a7.5 7.5 0 0 1 15 0V15')}<rect x="3.6" y="14" width="4" height="6" rx="1.6" /><rect x="16.4" y="14" width="4" height="6" rx="1.6" /></>,
  plug: <>{P('M9 3v4M15 3v4M7 7h10v3.5a5 5 0 0 1-10 0V7ZM12 15.5V21')}</>,
  laptop: <><rect x="5" y="5" width="14" height="10" rx="1.6" />{P('M3 18.5h18')}</>,
  camera: <><rect x="3.5" y="7" width="17" height="12" rx="2.4" /><circle cx="12" cy="13" r="3.2" />{P('M9 7l1.2-2.2h3.6L15 7')}</>,
  watch: <><rect x="7" y="6.5" width="10" height="11" rx="3" />{P('M9 6.5 9.6 3h4.8l.6 3.5M9 17.5l.6 3.5h4.8l.6-3.5M12 10v2.2l1.4 1')}</>,
  appliance: <><rect x="6" y="3" width="12" height="18" rx="2.2" />{P('M6 9.5h12M9 6v1.6M9 12.5v2.6')}</>,
  tool: <>{P('M14.7 6.3a4 4 0 0 0-5.2 5.2L4 17l3 3 5.5-5.5a4 4 0 0 0 5.2-5.2l-2.4 2.4-2.3-.7-.7-2.3 2.4-2.4Z')}</>,
  shirt: <>{P('M9 4 4.5 6.5l1.8 4L8 9.8V20h8V9.8l1.7.7 1.8-4L15 4a3 3 0 0 1-6 0Z')}</>,
  beauty: <><rect x="8" y="9" width="8" height="12" rx="2.2" />{P('M10 9V6.5h4V9M11 3.5h2v3h-2z')}</>,
  book: <>{P('M5 4.5h5.5A2.5 2.5 0 0 1 13 7v13a2 2 0 0 0-2-2H5V4.5ZM19 4.5h-3.5A2.5 2.5 0 0 0 13 7v13a2 2 0 0 1 2-2h4V4.5Z')}</>,
  toy: <><circle cx="12" cy="13" r="6" /><circle cx="7" cy="6.5" r="2" /><circle cx="17" cy="6.5" r="2" />{P('M10 14.5c1.2 1 2.8 1 4 0')}</>,
  light: <>{P('M9 17h6M10 20.5h4M12 3a6 6 0 0 0-3.5 10.9c.4.3.5.7.5 1.1v2h5v-2c0-.4.1-.8.5-1.1A6 6 0 0 0 12 3Z')}</>,
  car: <>{P('M5 16.5V12l1.8-4.6A2 2 0 0 1 8.7 6h6.6a2 2 0 0 1 1.9 1.4L19 12v4.5M3.5 12h17v4.5h-17z')}<circle cx="7.5" cy="16.5" r="1.6" /><circle cx="16.5" cy="16.5" r="1.6" /></>,
  bed: <>{P('M3.5 18.5V7M3.5 13h17v5.5M20.5 13v-1.5a3 3 0 0 0-3-3H11v4.5')}<circle cx="7.2" cy="10.6" r="1.7" /></>,
  sport: <><circle cx="12" cy="12" r="8" />{P('M4.5 9.5c3 1 5.5 3.5 6.5 10.3M19.5 9.5c-3 1-5.5 3.5-6.5 10.3M8 4.8C10 7 14 7 16 4.8')}</>,
  bag: <>{P('M5.5 8h13l-1 12h-11l-1-12ZM9 8V6.5a3 3 0 0 1 6 0V8')}</>,
}
const RULES: [RegExp, string][] = [
  [/کنسول|بازی|گیم|پلی ?استیشن|ایکس ?باکس|دسته/, 'game'],
  [/هدفون|هندزفری|هدست|اسپیکر|صوتی|ایرپاد|بلندگو/, 'headphone'],
  [/گوشی|موبایل|تبلت|سیم ?کارت|ال ?سی ?دی|تاچ/, 'phone'],
  [/شارژر|کابل|آداپتور|پاور ?بانک|برق|کلید|پریز|سیم |باتری|ups/i, 'plug'],
  [/لپ ?تاپ|کامپیوتر|مانیتور|ماوس|کیبورد|پرینتر|هارد|رم |کارت گرافیک|مودم|روتر|شبکه/, 'laptop'],
  [/دوربین|نظارتی|امنیتی|دزدگیر/, 'camera'],
  [/ساعت|مچ ?بند/, 'watch'],
  [/یخچال|لباسشویی|ظرفشویی|جارو|اجاق|مایکروویو|آشپز|کولر|بخاری|اتو|سرخ ?کن|چای ?ساز|قهوه|مخلوط|خردکن|خانگی/, 'appliance'],
  [/ابزار|دریل|فرز|پیچ ?گوشتی|آچار|اره|صنعتی|جوش/, 'tool'],
  [/پیراهن|شلوار|کفش|کیف|لباس|مانتو|تیشرت|پوشاک|کاپشن|جوراب|شال|روسری/, 'shirt'],
  [/عطر|ادکلن|آرایش|کرم|شامپو|مو |اصلاح|بهداشت|پوست|ریش/, 'beauty'],
  [/کتاب|دفتر|خودکار|تحریر|مداد|لوازم التحریر/, 'book'],
  [/اسباب ?بازی|عروسک|کودک|نوزاد|فیگور|لگو/, 'toy'],
  [/لامپ|چراغ|لوستر|روشنایی|ال ?ای ?دی/, 'light'],
  [/خودرو|ماشین|موتور ?سیکلت|لاستیک/, 'car'],
  [/تشک|تخت|مبل|میز|صندلی|کمد|مبلمان|فرش|پرده/, 'bed'],
  [/ورزش|دوچرخه|کوه|کمپ|توپ|تردمیل|دمبل|اسکیت/, 'sport'],
]
const PAL: [string, string][] = [
  ['#efedfb', '#5a53c8'], ['#fdecef', '#c8566b'], ['#e7f4ec', '#3c8f62'], ['#fcf3e3', '#b98327'],
  ['#e8eef9', '#3f5f9e'], ['#e4f3f3', '#2d8484'],
]
export function catKey(name?: string | null) {
  const n = name || ''
  for (const [re, k] of RULES) if (re.test(n)) return k
  return 'bag'
}
export function catLook(name?: string | null) {
  const n = (name || '').trim()
  let h = 0
  for (let i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) >>> 0
  const [bg, fg] = PAL[n ? h % PAL.length : 0]
  return { key: catKey(n), bg, fg }
}
export function CatGlyph({ k, size = 22, color = 'currentColor', sw = 1.7 }: { k: string; size?: number; color?: string; sw?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {ICONS[k] || ICONS.bag}
    </svg>
  )
}
export function CatTile({ name, size = 44, radius = 14, icon = 22, style }: { name?: string | null; size?: number; radius?: number; icon?: number; style?: CSSProperties }) {
  const l = catLook(name)
  return (
    <span className="cat-tile" style={{ width: size, height: size, borderRadius: radius, background: l.bg, color: l.fg, ...style }}>
      <CatGlyph k={l.key} size={icon} />
    </span>
  )
}
/** first clause of a long category name: «هدفون، هدست و هندزفری» -> «هدفون» */
export const catShort = (n?: string | null) => (n || '').split(/[،,]/)[0].replace(/\s+/g, ' ').trim()
