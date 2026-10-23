// Shop sheet (design 5/6), contact sheet (number as TEXT + copy, no tel:), and the «ترب چی رو پیگیری کنه؟» UI mock (design 7).
import { MallGuide } from './mallguide/MallGuide'
import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { api, errText, SID } from './api'
import { clean, fa, faNum, host, short, splitTitle, UNKNOWN } from './fmt'
import { CardIcon, ChevLeft, Close, CopyIcon, GlobeIcon, Heart, InstaIcon, NavIcon, PhoneIcon, Pin, ShareIcon, TruckIcon } from './icons'

const AltIcon = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M7 7h11l-3-3M17 17H6l3 3" /></svg>
import { Composer, Img, MascotAvatar, type Attachment } from './ui'
import { CatGlyph, catLook, catShort, CatTile } from './catIcon'

type Hours = { day: string; hours: string; today: boolean }
export type ShopR = {
  shop_id: string; name: string; address: string; area: string; place: string; lat: number | null; lon: number | null
  hours: Hours[] | null; payment_options: { provider: string; channel: string }[]; fast_delivery: boolean | null
  website: string | null; instagram: string | null; phone_display: string | null; phone_note: string | null; n_products: number
  open_now: { known: boolean; open: boolean | null; until?: string; label: string }; main_categories: { name: string; n_products: number }[]
  installment: boolean; installment_providers: string[]; directions_url: string | null; osm_url: string | null
  open_state?: 'open' | 'closed_now' | 'closed_today' | 'unknown'; open_badge?: string | null
  routes?: { google: string; neshan: string } | null
  location?: Loc | null
  offer: null | { product_id: string; title: string; model: string | null; image: string | null; price_toman: number | null; warranty_info: { has: boolean; label: string | null }; updated_fa: string; stale: boolean; suspicious: boolean }
}
type QA = { q: string; a?: string; err?: string }
type WebLoc = { status: string; floor: string | null; unit: string | null; landmark: string | null; source_url: string | null; source_title?: string | null; cached?: boolean }
type Loc = { in_mall: boolean; mall: string | null; floor_label: string | null; unit_label: string | null; block: string | null; needs_lookup: boolean; web: WebLoc | null }
type Alt = { offer_id: string; product_id: string; same_product: boolean; product_title: string; shop_id: string; shop_name: string; price_toman: number; place: string
  distance_label: string; open_badge: string; is_open: boolean; routes: { google: string; neshan: string } | null }
export type AltR = { shop_name: string; product_title: string; basis: string; items: Alt[] }

const MALL_PREFIX = /^(پاساژ|مجتمع\s*تجاری|مجتمع|مرکز\s*خرید|ساختمان\s*تجاری|سرای|برج\s*تجاری)\s*/
/** one quiet line: «📍 علاالدین · طبقهٔ ۴ · پلاک ۴۲۲» (+ cited web info); «پیدا کردن جای دقیق» as a small link only when floor/unit is missing */
function LocLine({ sid, loc, place }: { sid: string; loc: Loc | null | undefined; place: string }) {
  const [web, setWeb] = useState<WebLoc | null>(loc?.web || null)
  const [busy, setBusy] = useState(false)
  const find = async () => {
    setBusy(true)
    try { setWeb(await api<WebLoc>(`/api/shop/${encodeURIComponent(sid)}/place/find`, { body: {}, timeout: 60000 })) } catch { setWeb({ status: 'error', floor: null, unit: null, landmark: null, source_url: null }) } finally { setBusy(false) }
  }
  const wok = web?.status === 'ok'
  const parts = loc?.in_mall
    ? [loc.mall ? loc.mall.replace(MALL_PREFIX, '') : null, loc.block && loc.block !== loc.mall ? loc.block : null, loc.floor_label, loc.unit_label]
    : [place && place !== UNKNOWN ? place : null]
  if (wok) parts.push(...[web!.floor, web!.unit].filter((x) => x && !parts.some((p) => p && fa(p).includes(fa(x!)))))
  const line = parts.filter(Boolean).map((x) => fa(x!)).join(' · ')
  if (!line) return null
  return (
    <div className="cs-loc">
      <span className="cs-loc-t"><Pin size={13} color="#9a9bab" /> {line}</span>
      {wok && web!.source_url ? <a className="cs-link sm" href={web!.source_url} target="_blank" rel="noreferrer">منبع</a>
        : web ? <span className="cs-muted">جای دقیق نامشخص</span>
        : loc?.needs_lookup ? <button className="cs-link sm" onClick={find} disabled={busy}>{busy ? 'در حال جست‌وجو…' : 'پیدا کردن جای دقیق'}</button> : null}
    </div>
  )
}

/** «بسته بود؟ جایگزین بده»: 3 nearest other shops with the same product that are open now (or hours unknown); DB only */
export function AltList({ sid, pid, onShop }: { sid: string; pid: string; onShop?: (sid: string, pid: string) => void }) {
  const [r, setR] = useState<AltR | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    api<AltR>(`/api/shop/${encodeURIComponent(sid)}/alternatives?product_id=${encodeURIComponent(pid)}`).then((x) => alive && setR(x)).catch((e) => alive && setErr(errText(e)))
    return () => { alive = false }
  }, [sid, pid])
  if (err) return <p className="cs-muted pad">{err}</p>
  if (!r) return <p className="cs-muted pad">در حال پیدا کردن جایگزین…</p>
  return <AltBox r={r} onShop={onShop} />
}
/** clean list: name · area word (right), price + tiny status dot (left), thin dividers, no container */
export function AltBox({ r, onShop }: { r: AltR; onShop?: (sid: string, pid: string) => void }) {
  return (
    <div className="cs-alt">
      <div className="cs-sec">جایگزین‌های نزدیک · {r.basis === 'same_product' ? 'همین محصول' : 'همین محصول یا مدل'}</div>
      {r.items.length ? r.items.map((x) => (
        <button key={x.offer_id} className="cs-alt-row" onClick={() => onShop?.(x.shop_id, x.product_id)}>
          <span className="cs-alt-c"><span className="cs-alt-n">{x.shop_name}</span><span className="cs-alt-a">{x.place} · {x.distance_label}{x.same_product ? '' : ' · همین مدل'}</span></span>
          <span className="cs-alt-p"><i className={'cs-dot' + (x.is_open ? ' on' : '')} title={x.open_badge} aria-label={x.open_badge} />{faNum(x.price_toman)} <small>تومان</small></span>
        </button>
      )) : <p className="cs-muted pad">فروشگاه بازِ دیگری با همین محصول پیدا نشد.</p>}
      {r.items.length ? <div className="cs-legend"><i className="cs-dot on" /> الان بازه <i className="cs-dot" /> ساعت نامشخص</div> : null}
    </div>
  )
}

async function copy(t: string, toast: (s: string) => void) {
  try { await navigator.clipboard.writeText(t); toast('کپی شد') } catch {
    const ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy'); toast('کپی شد') } catch { toast('کپی نشد') } finally { ta.remove() }
  }
}

/** consecutive days with the same hours collapse into one row; today always gets its own highlighted row */
function hourRows(h: Hours[]) {
  const rows: { label: string; hours: string; today: boolean }[] = []
  let i = 0
  while (i < h.length) {
    if (h[i].today) { rows.push({ label: h[i].day + '، امروز', hours: h[i].hours, today: true }); i++; continue }
    let j = i
    while (j + 1 < h.length && !h[j + 1].today && h[j + 1].hours === h[i].hours) j++
    rows.push({ label: j > i ? `${h[i].day} تا ${h[j].day}` : h[i].day, hours: h[i].hours, today: false })
    i = j + 1
  }
  return rows
}

function AddrMap({ lat, lon, cat }: { lat: number; lon: number; cat: string }) {
  const el = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!el.current) return
    const m = L.map(el.current, { zoomControl: false, attributionControl: true, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, touchZoom: false, keyboard: false })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(m)
    m.attributionControl.setPrefix(false)
    const svg = el.current.parentElement?.querySelector('.addr-glyph')?.innerHTML || ''
    L.marker([lat, lon], { icon: L.divIcon({ className: 'shop-pin', html: `<span>${svg}</span>`, iconSize: [40, 50], iconAnchor: [20, 48] }), interactive: false }).addTo(m)
    m.setView([lat, lon], 16)
    const ro = new ResizeObserver(() => m.invalidateSize()); ro.observe(el.current)
    return () => { ro.disconnect(); m.remove() }
  }, [lat, lon])
  return <><span className="addr-glyph" hidden><CatGlyph k={cat} size={18} color="#fff" sw={1.9} /></span><div ref={el} className="lf addr-map" /></>
}

function FloatSheet({ children, onClose, closing }: { children: React.ReactNode; onClose: () => void; closing: boolean }) {
  const [open, setOpen] = useState(false)
  useEffect(() => { const r = requestAnimationFrame(() => setOpen(true)); return () => cancelAnimationFrame(r) }, [])
  return (
    <div className={'fsheet-wrap' + (open && !closing ? ' open' : '')}>
      <div className="sheet-scrim" onClick={onClose} />
      <div className="fsheet" role="dialog">{children}</div>
    </div>
  )
}
/** close with the same slide-down animation */
function useClosing(onDone: () => void): [boolean, () => void] {
  const [c, setC] = useState(false)
  return [c, () => { if (c) return; setC(true); window.setTimeout(onDone, 300) }]
}

export function ContactSheet({ s, onClose, toast }: { s: ShopR; onClose: () => void; toast: (t: string) => void }) {
  const [closing, close] = useClosing(onClose)
  return (
    <FloatSheet onClose={close} closing={closing}>
      <div className="fs-h"><b>تماس با {s.name}</b><button className="circ sm grey" onClick={close} aria-label="بستن"><Close /></button></div>
      {s.phone_display ? (
        <>
          <div className="phone-box"><span dir="ltr">{s.phone_display}</span><button className="circ grey" onClick={() => copy(s.phone_display!, toast)} aria-label="کپی شماره"><CopyIcon /></button></div>
          {s.phone_note ? <p className="fs-note">{s.phone_note}</p> : null}
        </>
      ) : <p className="fs-note">برای این فروشگاه شماره‌ای ثبت نشده است.</p>}
    </FloatSheet>
  )
}

const FOLLOW = ['الان این محصول رو دارن؟', 'آخرین قیمت و تخفیف', 'امکان قسطی', 'کنار گذاشتن تا امروز عصر']
/** UI mock only: selectable items; the button just closes the sheet. No backend call, nothing posted to chat. */
export function FollowSheet({ onClose, onAlt }: { onClose: () => void; onAlt?: () => void }) {
  const [sel, setSel] = useState<Record<number, boolean>>({ 0: true })
  const [closing, close] = useClosing(onClose)
  return (
    <FloatSheet onClose={close} closing={closing}>
      <div className="fs-h">
        <span className="fs-ht"><MascotAvatar state="idle" size={40} /><b>ترب چی رو پیگیری کنه؟</b></span>
        <button className="circ sm grey" onClick={close} aria-label="بستن"><Close /></button>
      </div>
      <div className="qlist">
        {FOLLOW.map((t, i) => (
          <button key={t} className={'qrow' + (sel[i] ? ' on' : '')} aria-pressed={!!sel[i]} onClick={() => setSel((x) => ({ ...x, [i]: !x[i] }))}>
            <span className="qnum">{fa(i + 1)}</span><span className="qlab">{t}</span>
          </button>
        ))}
      </div>
      <button className="btn-ink wide" onClick={close}><PhoneIcon size={18} /> زنگ بزن و نتیجه رو بگو</button>
      <p className="fs-sub">نتیجه توی چت برات میاد</p>
      {onAlt ? <button className="cs-link center" onClick={() => { close(); window.setTimeout(onAlt, 320) }}>جواب ندادن؟ جایگزین‌های باز نزدیک ←</button> : null}
    </FloatSheet>
  )
}

export function ShopSheet({ sid, pid, sbar, onClose, onProduct, toast, onShop, alt }: {
  sid: string; pid?: string | null; sbar: boolean; onClose: () => void; onProduct: (pid: string) => void; toast: (t: string) => void
  onShop?: (sid: string, pid: string) => void; alt?: boolean
}) {
  const [altOn, setAltOn] = useState(!!alt)
  const [routePick, setRoutePick] = useState(false)
  const [s, setS] = useState<ShopR | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [sub, setSub] = useState<null | 'contact' | 'follow'>(null)
  const [fav, setFav] = useState(() => !!localStorage.getItem('torob_fav_shop_' + sid))
  const [value, setValue] = useState('')
  const [att, setAtt] = useState<Attachment | null>(null)
  const [qa, setQa] = useState<QA[]>([])
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => { const r = requestAnimationFrame(() => setOpen(true)); return () => cancelAnimationFrame(r) }, [])
  useEffect(() => {
    let alive = true
    setErr(null)
    api<ShopR>(`/api/home/shop/${encodeURIComponent(sid)}` + (pid ? `?product_id=${encodeURIComponent(pid)}` : '')).then((r) => alive && setS(r)).catch((e) => alive && setErr(errText(e)))
    api('/api/memory/select', { body: { sid: SID, version: 'v3plus', kind: 'shop', id: sid, product_id: pid || undefined } }).catch(() => {})
    return () => { alive = false }
  }, [sid, pid, tick])
  useEffect(() => { if (qa.length) { const el = scroller.current; el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }) } }, [qa])
  const close = () => { setOpen(false); window.setTimeout(onClose, 300) }
  const ask = async (q: string) => {
    if (!q.trim() || busy || !s) return
    setQa((x) => [...x, { q }]); setValue(''); setAtt(null); setBusy(true)
    try {
      const j = await api<{ results: { ok?: boolean; text: string }[] }>('/api/send', { body: { message: q, sid: SID + '_shop', mode: 'v3plus', shop_id: s.shop_id, product_id: pid || undefined }, timeout: 120000 })
      const r = j.results[0]
      setQa((x) => x.map((y, i) => (i === x.length - 1 ? (r.ok === false ? { q, err: 'نشد جواب بدم؛ یه بار دیگه بپرس.' } : { q, a: r.text }) : y)))
    } catch (e) { setQa((x) => x.map((y, i) => (i === x.length - 1 ? { q, err: errText(e) } : y))) } finally { setBusy(false) }
  }
  const share = async () => {
    if (!s) return
    const text = `${s.name}\n${s.address}` + (s.osm_url ? `\n${s.osm_url}` : '')
    try { if (navigator.share) { await navigator.share({ title: s.name, text }); return } } catch { return }
    copy(text, toast)
  }
  const toggleFav = () => { const n = !fav; setFav(n); if (n) localStorage.setItem('torob_fav_shop_' + sid, '1'); else localStorage.removeItem('torob_fav_shop_' + sid); toast(n ? 'به فروشگاه‌های محبوب اضافه شد' : 'از محبوب‌ها برداشته شد') }
  const main = s?.main_categories?.[0]?.name || null
  const subtitle = s?.main_categories?.length ? [...new Set(s.main_categories.slice(0, 2).map((c) => catShort(c.name)))].join('، ') : null
  const pay = s?.payment_options?.length ? [...new Set(s.payment_options.map((p) => p.provider))].join('، ') + (s.installment ? ' (قسطی)' : '') : null
  const o = s?.offer
  const [oFa, oLat] = splitTitle(o?.title)
  const closed = s?.open_state === 'closed_now' || s?.open_state === 'closed_today'
  const routes = s?.routes || (s?.directions_url ? { google: s.directions_url, neshan: s.directions_url } : null)
  return (
    <div className={'sheet-wrap shop-wrap' + (open ? ' open' : '')}>
      <div className="sheet-scrim" onClick={close} />
      <div className={'sheet shop-sheet' + (sbar ? ' framed' : '')} role="dialog">
        <div className="sheet-grab" aria-hidden />
        <div className="shop-top">
          <button className="circ" onClick={close} aria-label="بستن"><Close /></button>
          <span style={{ flex: 1 }} />
          <button className="circ" onClick={share} aria-label="اشتراک‌گذاری"><ShareIcon size={18} /></button>
          <button className="circ" onClick={toggleFav} aria-label="محبوب"><Heart on={fav} /></button>
        </div>
        <div className="shop-scroll" ref={scroller}>
          {err ? (
            <div className="empty"><MascotAvatar state="think" size={64} /><p>{err}</p><button className="btn-dark" onClick={() => setTick((t) => t + 1)}>تلاش دوباره</button></div>
          ) : !s ? (
            <div className="empty"><MascotAvatar state="search" size={64} /><p>در حال آوردن اطلاعات فروشگاه…</p></div>
          ) : (
            <>
              <div className="cs-head">
                <CatTile name={main} size={52} radius={16} icon={24} />
                <div className="cs-head-c">
                  <h2>{s.name}</h2>
                  <div className="cs-sub">
                    <span className={'cs-status ' + (s.open_now.open ? 'on' : closed ? 'off' : 'unk')}><i className="cs-dot" />
                      {s.open_now.open ? `باز تا ${fa(s.open_now.until)}` : s.open_state === 'closed_today' ? 'امروز تعطیل' : s.open_state === 'closed_now' ? 'الان بسته' : 'ساعت نامشخص'}</span>
                    {subtitle ? <span className="cs-cat">{subtitle}</span> : null}
                  </div>
                </div>
              </div>
              <LocLine sid={s.shop_id} loc={s.location} place={s.place} />
              <MallGuide sid={s.shop_id} pid={pid} sbar={sbar}
                onContact={() => setSub('contact')}
                onAsk={() => scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })} />
              <div className="cs-actions">
                {routes ? <button className="cs-primary" onClick={() => setRoutePick((x) => !x)} aria-expanded={routePick}><NavIcon size={18} /> مسیریابی</button>
                  : <button className="cs-primary" disabled>موقعیت ثبت نشده</button>}
                {routePick && routes ? <div className="cs-route"><a href={routes.neshan} target="_blank" rel="noreferrer">نشان</a><span>·</span><a href={routes.google} target="_blank" rel="noreferrer">گوگل‌مپ</a></div> : null}
                <div className="cs-sec-acts">
                  <button onClick={() => setSub('contact')}><PhoneIcon size={15} /> تماس</button>
                  <button onClick={() => setSub('follow')}><MascotAvatar state="idle" size={20} /> ترب برام زنگ بزنه</button>
                  {o && pid ? <button onClick={() => setAltOn((x) => !x)} aria-pressed={altOn}><AltIcon /> جایگزین</button> : null}
                </div>
              </div>
              {closed && o && pid && !altOn ? <button className="cs-closed-link" onClick={() => setAltOn(true)}>الان بسته‌ست · جایگزین‌های باز نزدیک ←</button> : null}
              {altOn && o && pid ? <AltList sid={s.shop_id} pid={pid} onShop={onShop} /> : null}
              {o ? (
                <>
                  <div className="cs-sec top">این محصول اینجا</div>
                  <button className="cs-prod" onClick={() => onProduct(o.product_id)}>
                    <span className="cs-prod-im"><Img src={o.image} /></span>
                    <span className="cs-prod-t" dir={oLat ? 'ltr' : undefined}>{oLat || short(oFa, 40)}</span>
                    <span className="cs-prod-p">{o.price_toman ? <span>{faNum(o.price_toman)} <small>تومان</small></span> : <small>{UNKNOWN}</small>}
                      {o.stale || o.suspicious ? <em>{o.suspicious ? 'قیمت مشکوک' : 'قیمت قدیمی'}</em> : null}</span>
                  </button>
                </>
              ) : null}
              {s.main_categories.length ? (
                <>
                  <div className="shop-sec row"><h3>دسته‌بندی‌ها</h3><small>{fa(s.n_products)} محصول</small></div>
                  <div className="cat-grid">
                    {s.main_categories.map((c) => {
                      const l = catLook(c.name)
                      return <div className="cat-cell" key={c.name}><span className="cat-big" style={{ background: l.bg, color: '#2c2d45' }}><CatGlyph k={l.key} size={24} /></span><b>{short(catShort(c.name), 14)}</b></div>
                    })}
                  </div>
                </>
              ) : null}
              {s.hours?.length ? (
                <>
                  <h3 className="shop-sec">ساعت کاری</h3>
                  <div className="hcard">{hourRows(s.hours).map((r, i) => <div key={i} className={'hr-row' + (r.today ? ' today' : '')}><span>{r.today ? <i /> : null}{r.label}</span><b>{r.hours}</b></div>)}</div>
                </>
              ) : null}
              <h3 className="shop-sec">آدرس</h3>
              <div className="addr-card">
                {s.lat != null && s.lon != null ? <AddrMap lat={s.lat} lon={s.lon} cat={catLook(main).key} /> : null}
                <div className="addr-row"><span>{s.address !== UNKNOWN ? clean(s.address) : UNKNOWN}</span>
                  {s.address !== UNKNOWN ? <button className="circ grey" onClick={() => copy(s.address, toast)} aria-label="کپی آدرس"><CopyIcon /></button> : null}</div>
              </div>
              <h3 className="shop-sec">اطلاعات فروشگاه</h3>
              <div className="icard">
                <div className="irow"><span className="iic"><CardIcon /></span><span className="ic"><small>روش پرداخت</small><b>{pay || UNKNOWN}</b></span></div>
                {s.fast_delivery !== null ? <div className="irow"><span className="iic"><TruckIcon /></span><span className="ic"><small>ارسال</small><b>{s.fast_delivery ? 'ارسال سریع دارد' : 'ارسال سریع ندارد'}</b></span></div> : null}
                {s.phone_display ? <div className="irow"><span className="iic"><PhoneIcon /></span><span className="ic"><small>تلفن</small><b dir="ltr">{s.phone_display}</b>{s.phone_note ? <em>{s.phone_note}</em> : null}</span>
                  <button className="circ grey" onClick={() => copy(s.phone_display!, toast)} aria-label="کپی شماره"><CopyIcon /></button></div> : null}
                {s.instagram ? <a className="irow" href={/^https?:/.test(s.instagram) ? s.instagram : 'https://instagram.com/' + s.instagram.replace(/^@/, '')} target="_blank" rel="noreferrer"><span className="iic"><InstaIcon /></span><span className="ic"><small>اینستاگرام</small><b dir="ltr">@{s.instagram.replace(/^@/, '').replace(/^https?:\/\/(www\.)?instagram\.com\//, '').replace(/\/$/, '')}</b></span><span className="chev-c"><ChevLeft size={9} /></span></a> : null}
                {s.website ? <a className="irow" href={s.website} target="_blank" rel="noreferrer"><span className="iic"><GlobeIcon /></span><span className="ic"><small>وب‌سایت</small><b dir="ltr">{host(s.website)}</b></span><span className="chev-c"><ChevLeft size={9} /></span></a> : null}
              </div>
              {qa.length ? (
                <div className="shop-qa">
                  {qa.map((x, i) => (
                    <div key={i}>
                      <div className="qa-u">{x.q}</div>
                      <div className="bot-row"><MascotAvatar state={x.a || x.err ? 'idle' : 'think'} size={36} />
                        <div className={'bubble-b' + (!x.a && !x.err ? ' typing' : '')}>{x.a ? x.a : x.err ? x.err : <><span>دارم نگاه می‌کنم</span><i /><i /><i /></>}</div></div>
                    </div>
                  ))}
                </div>
              ) : null}
              <div style={{ height: 8 }} />
            </>
          )}
        </div>
        {s ? (
          <div className="shop-foot">
            <div className="qchips">{['الان بازه؟', 'قسطی می‌ده؟'].map((t) => <button key={t} onClick={() => ask(t)} disabled={busy}>{t}</button>)}</div>
            <div className="shop-comp">
              <Composer variant="chat" value={value} onChange={setValue} onSubmit={() => ask(value)} placeholder="دربارهٔ این فروشگاه از ترب بپرس..." attachment={att} onAttach={setAtt} busy={busy}
                end={<MascotAvatar state={busy ? 'think' : 'idle'} size={42} />} />
            </div>
          </div>
        ) : null}
        {s && sub === 'contact' ? <ContactSheet s={s} onClose={() => setSub(null)} toast={toast} /> : null}
        {s && sub === 'follow' ? <FollowSheet onClose={() => setSub(null)} onAlt={o && pid ? () => setAltOn(true) : undefined} /> : null}
      </div>
    </div>
  )
}
