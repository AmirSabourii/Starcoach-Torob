import { useMemo, useState } from 'react'
import { api, CID, errText } from './api'
import { fa, faNum, short, toman, UNKNOWN } from './fmt'
import { BackIcon, MapIcon, ShareIcon, Heart } from './icons'
import { Composer, Img, MascotAvatar, type Attachment } from './ui'
import { LeafletPins } from './MapView'

export type Need = { id: string; item: string; query: string; qty: number; unit: string; priority: 'essential' | 'optional'; why?: string; specs?: string; enabled?: boolean; [k: string]: unknown }
export type ProjectR = { stage: string; goal: string; title: string; assumptions?: string | string[]; area?: string | null; needs: Need[] }
type Row = { need_id: string; item: string; qty: number; unit: string; product_id: string; title: string; image: string | null; offer_id: string; shop_id: string; shop_name: string; shop_area: string; price_toman: number | null; line_total_toman: number | null; stale: boolean; date_fa: string; compat_badge?: string; incompatible?: boolean }
type Plan = { key: string; name: string; also?: string[]; total_toman: number | null; total_is_partial: boolean; n_unknown: number; n_items_found: number; n_shops: number; n_stale: number; spread_km: number; hub: { name: string; all_shops_in_hub: boolean } | null; system_label?: string; n_incompatible?: number; n_unverified?: number; shops: { shop_id: string; name: string; lat: number; lon: number; n_items: number }[]; rows: Row[] }
export type SearchR = { plans: Plan[]; not_found: { need_id: string; item: string; alternative: { product_id: string; title: string } | null }[]; summary: string; area: string | null; selected?: string; revision?: string; title?: string; goal?: string; needs?: Need[] }

export const TAB: Record<string, string> = { cheapest: 'ارزان‌ترین', one_stop: 'کمترین فروشگاه', balanced: 'متعادل' }

export function ProjectChecklist({ p, area, areaLabel, onSearched }: { p: ProjectR; area: string; areaLabel: string; onSearched: (r: SearchR, sent: number, p: ProjectR) => void }) {
  const [needs, setNeeds] = useState<Need[]>(() => p.needs.map((n) => ({ ...n, enabled: n.enabled !== false })))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const on = needs.filter((n) => n.enabled)
  const assumptions = Array.isArray(p.assumptions) ? p.assumptions : p.assumptions ? [p.assumptions] : []
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api<SearchR>('/api/project/search', { body: { needs: on, area: area || null, goal: p.goal }, timeout: 60000 })
      onSearched(r, on.length, p)
    } catch (e) { setErr(errText(e)) } finally { setBusy(false) }
  }
  return (
    <div className="proj">
      <div className="proj-h"><span className="proj-ic">🧺</span><div><small>خرید یکجا</small><b>{p.title}</b></div></div>
      {assumptions.length ? <div className="dr-chips wrap">{assumptions.map((a, i) => <span key={i} className="chip-s">{a}</span>)}</div> : null}
      {needs.map((n, i) => (
        <div className={'nrow' + (n.enabled ? '' : ' off')} key={n.id || i}>
          <button className={'tick' + (n.enabled ? ' on' : '')} aria-label="انتخاب" onClick={() => setNeeds((x) => x.map((y, j) => (j === i ? { ...y, enabled: !y.enabled } : y)))}>{n.enabled ? '✓' : ''}</button>
          <div className="nrow-c">
            <b>{n.item} <span className={'pri' + (n.priority === 'optional' ? ' opt' : '')}>{n.priority === 'optional' ? 'اختیاری' : 'ضروری'}</span></b>
            {n.why ? <small>{n.why}</small> : null}
          </div>
          <div className="qty">
            <button onClick={() => setNeeds((x) => x.map((y, j) => (j === i ? { ...y, qty: Math.max(1, (y.qty || 1) - 1) } : y)))}>−</button>
            <span>{fa(n.qty || 1)}<small>{n.unit || 'عدد'}</small></span>
            <button onClick={() => setNeeds((x) => x.map((y, j) => (j === i ? { ...y, qty: Math.min(500, (y.qty || 1) + 1) } : y)))}>+</button>
          </div>
        </div>
      ))}
      <div className="proj-area">محدودهٔ خرید: <b>{areaLabel}</b></div>
      {err ? <div className="err">{err}</div> : null}
      <button className="btn-dark wide" disabled={busy || !on.length} onClick={go}>{busy ? 'در حال جستجو…' : `جستجوی همه · ${fa(on.length)} قلم`}</button>
    </div>
  )
}

/** compact plan context for follow-up turns (/api/send `project`) */
export function planContext(p: ProjectR, plan: Plan | undefined, r: SearchR) {
  if (!plan) return null
  return { title: p.title, goal: p.goal, plan: TAB[plan.key] || plan.name, total_toman: plan.total_toman, n_shops: plan.n_shops, area: r.area,
    items: plan.rows.map((x) => ({ item: x.item, qty: x.qty, product_id: x.product_id, product: short(x.title, 50), shop: x.shop_name, area: x.shop_area, price_toman: x.price_toman })),
    not_found: r.not_found.map((n) => n.item) }
}
const FOLLOW = (area: string, item?: string) => ['ارزون‌ترش کن', 'فقط از یه بازار', item ? `${item.split(/\s+/).slice(0, 2).join(' ')} رو عوض کن` : 'یه گزینهٔ دیگه بده', `نزدیک ${area} باشه`]

export function ProjectResults({ r, sent, p, onBack, onShop, onProduct, toast, onFollow, areaLabel, start, busy: chatBusy }: { r: SearchR; start?: [number, number]; sent: number; p: ProjectR; onBack: () => void; onShop: (s: string) => void; onProduct: (pid: string) => void; toast: (t: string) => void
  onFollow: (text: string, ctx: Record<string, unknown> | null) => void; areaLabel: string; busy: boolean }) {
  const [value, setValue] = useState('')
  const [att, setAtt] = useState<Attachment | null>(null)
  const plans = r.plans
  const [key, setKey] = useState((r.selected && plans.find((x) => x.key === r.selected)?.key) || plans.find((x) => x.key === 'balanced')?.key || plans[0]?.key)
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const cur = plans.find((x) => x.key === key) || plans[0]
  const pins = useMemo(() => (cur ? cur.shops.filter((s) => s.lat != null) : []), [cur])
  const save = async () => {
    if (!cur) return
    setBusy(true)
    try {
      await api('/api/project/save', { body: { cid: CID, name: (p.title || 'خرید یکجا').slice(0, 26) + ' · ' + (TAB[cur.key] || cur.name), rows: cur.rows.map((x) => ({ product_id: x.product_id, shop_id: x.shop_id, offer_id: x.offer_id, qty: x.qty })) } })
      setSaved((s) => ({ ...s, [cur.key]: true })); toast('در «لیست‌های من» ذخیره شد')
    } catch (e) { toast(errText(e)) } finally { setBusy(false) }
  }
  const follow = (t: string) => { if (!t.trim() || chatBusy) return; onFollow(t.trim(), planContext(p, cur, r)); setValue('') }
  const route = () => {
    const pts = (cur?.shops || []).filter((s) => s.lat != null)
    if (!pts.length) { toast('موقعیت فروشگاه‌ها ثبت نشده'); return }
    // nearest-neighbour order from the shopper's area (else from the first shop), then one Google Maps multi-stop link
    const d = (a: [number, number], b: [number, number]) => Math.hypot(a[0] - b[0], (a[1] - b[1]) * Math.cos((a[0] * Math.PI) / 180))
    const rest = [...pts], ord: typeof pts = []
    let c: [number, number] = start && start[0] ? start : [rest[0].lat, rest[0].lon]
    while (rest.length) { rest.sort((a, b) => d(c, [a.lat, a.lon]) - d(c, [b.lat, b.lon])); const n = rest.shift()!; ord.push(n); c = [n.lat, n.lon] }
    const stops = ord.slice(0, 10), last = stops[stops.length - 1]
    const wp = stops.slice(0, -1).map((s) => `${s.lat.toFixed(6)},${s.lon.toFixed(6)}`).join('|')
    toast('ترتیب: ' + stops.map((s) => s.name).join(' ← '))
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${last.lat.toFixed(6)},${last.lon.toFixed(6)}` + (wp ? `&waypoints=${encodeURIComponent(wp)}` : '') + '&travelmode=walking', '_blank', 'noopener')
  }
  const share = async () => {
    if (!cur) return
    const lines = [`${p.title} · ${TAB[cur.key] || cur.name}`, ...cur.rows.map((x) => `• ${x.item} × ${fa(x.qty)}: ${short(x.title, 40)} — ${x.shop_name} (${toman(x.line_total_toman)})`), `جمع: ${toman(cur.total_toman)}`]
    const text = lines.join('\n')
    try { if (navigator.share) { await navigator.share({ title: p.title, text }); return } } catch { return }
    try { await navigator.clipboard.writeText(text); toast('فهرست خرید کپی شد') } catch { toast('کپی نشد') }
  }
  const pinNo = (sid: string) => (cur ? cur.shops.findIndex((s) => s.shop_id === sid) + 1 : 0)
  return (
    <div className="screen-page proj-page">
      <div className="page-h"><button className="icon-btn" onClick={onBack} aria-label="بازگشت"><BackIcon /></button><h1>خرید یکجا</h1><span style={{ width: 36 }} /></div>
      <div className="page-scroll">
        {!plans.length ? (
          <div className="empty"><MascotAvatar state="think" size={64} /><p>برای این اقلام پیشنهاد قیمت‌داری در داده‌ها پیدا نشد.</p></div>
        ) : (
          <>
            <div className="plan-tabs">
              {plans.map((x) => <button key={x.key} className={x.key === cur.key ? 'on' : ''} onClick={() => setKey(x.key)}>{TAB[x.key] || x.name}{x.also?.length ? ' *' : ''}</button>)}
            </div>
            <div className="ptotal">
              <div className="ptotal-n">{cur.total_toman != null ? faNum(cur.total_toman) : UNKNOWN}<small>تومان</small></div>
              {cur.total_is_partial ? <div className="ptotal-s">(بدون اقلام قیمت‌نامشخص)</div> : null}
              <div className="dr-chips center">
                <span className="chip-w">{cur.n_shops > 1 ? (cur.spread_km < 1.5 ? 'همه همین نزدیکی' : 'کمی پراکنده') : 'همه از یک فروشگاه'}</span>
                <span className="chip-w">{fa(cur.n_shops)} فروشگاه</span>
                {cur.hub ? <span className="chip-w">📍 {cur.hub.name}</span> : null}
                {cur.system_label ? <span className="chip-w">{cur.system_label}</span> : null}
                {cur.n_incompatible ? <span className="chip-w red">{fa(cur.n_incompatible)} قلم ناسازگار احتمالی</span> : null}
              </div>
              <div className="pmap"><LeafletPins centre={null} pins={pins} onPin={onShop} numbered /></div>
            </div>
            {cur.also?.length ? <p className="muted-p">* این برنامه با «{cur.also.join('، ')}» یکی است.</p> : null}
            {cur.key === 'balanced' && r.summary ? <div className="bot-text summary">{r.summary}</div> : null}
            <div className="prows">
              {cur.rows.map((x) => (
                <div className="prow" key={x.need_id + x.offer_id}>
                  <button className="prow-im" onClick={() => onProduct(x.product_id)}><Img src={x.image} /></button>
                  <div className="prow-c">
                    <b onClick={() => onProduct(x.product_id)}>{x.item} × {fa(x.qty)} {x.unit}</b>
                    <small onClick={() => onProduct(x.product_id)}>{short(x.title, 60)}</small>
                    <button className="prow-shop" onClick={() => onShop(x.shop_id)}><span className="pn">{fa(pinNo(x.shop_id))}</span>{x.shop_name}{x.shop_area && x.shop_area !== UNKNOWN ? ` · ${x.shop_area}` : ''}</button>
                    <span>{x.compat_badge ? <span className="flag sus">{x.compat_badge}</span> : null}{x.stale ? <span className="flag stale">قدیمی</span> : null}</span>
                  </div>
                  <div className="prow-p"><b>{toman(x.line_total_toman)}</b>{x.qty > 1 && x.price_toman ? <small>هر عدد {faNum(x.price_toman)}</small> : null}</div>
                </div>
              ))}
              {r.not_found.map((n) => (
                <div className="prow nf" key={n.need_id}>
                  <div className="prow-c"><b>{n.item}</b><small>در داده‌ها پیدا نشد{n.alternative ? ' · نزدیک‌ترین گزینه:' : ''}</small>
                    {n.alternative ? <button className="prow-shop" onClick={() => onProduct(n.alternative!.product_id)}>{short(n.alternative.title, 50)}</button> : null}</div>
                  <div className="prow-p"><span className="unk">{UNKNOWN}</span></div>
                </div>
              ))}
            </div>
            <div style={{ height: 12 }} />
          </>
        )}
      </div>
      {plans.length ? (
        <div className="proj-foot">
          <div className="proj-acts">
            <button onClick={route}><MapIcon size={16} /> مسیر خرید روی نقشه</button>
            <button onClick={share}><ShareIcon size={16} /> اشتراک‌گذاری</button>
            <button onClick={save} disabled={busy || saved[cur.key]} className={saved[cur.key] ? 'on' : ''}><Heart on={!!saved[cur.key]} /> {saved[cur.key] ? 'ذخیره شد' : 'ذخیره'}</button>
          </div>
          <div className="nchips">{FOLLOW(areaLabel, cur.rows[0]?.item).map((t) => <button key={t} className="nchip txt" onClick={() => follow(t)} disabled={chatBusy}><span>{t}</span></button>)}</div>
          <Composer variant="chat" value={value} onChange={setValue} onSubmit={() => follow(value)} placeholder="دربارهٔ این خرید بپرس یا تغییرش بده..." attachment={att} onAttach={setAtt} busy={chatBusy} />
        </div>
      ) : null}
    </div>
  )
}

const REV: Record<string, string> = { cheaper: 'نسخهٔ ارزان‌تر', one_place: 'از یک بازار', nearer: 'فروشگاه‌های نزدیک‌تر' }
/** chat card for a plan follow-up («ارزون‌ترش کن» …): the revised «خرید یکجا» plan, opens the same plan screen */
export function PlanUpdateCard({ pr, onOpen }: { pr: SearchR; onOpen: (r: SearchR, sent: number, p: ProjectR) => void }) {
  const cur = pr.plans.find((x) => x.key === pr.selected) || pr.plans[0]
  if (!cur) return null
  const p: ProjectR = { stage: 'needs', goal: pr.goal || '', title: pr.title || 'خرید یکجا', area: pr.area, needs: pr.needs || [] }
  return (
    <div className="blk plan-upd">
      <div className="pu-t">🧺 {pr.title || 'خرید یکجا'} · <b>{REV[pr.revision || ''] || 'فهرست به‌روز شد'}</b></div>
      <div className="pu-row"><span>{TAB[cur.key] || cur.name}</span><span className="pu-tot">{cur.total_toman ? toman(cur.total_toman) : '—'}</span></div>
      <div className="pu-sub">{fa(cur.n_items_found)} قلم · {fa(cur.n_shops)} فروشگاه{cur.hub ? ' · ' + cur.hub.name : ''}{cur.system_label ? ' · ' + cur.system_label : ''}</div>
      <button className="btn-ink pu-btn" onClick={() => onOpen(pr, Date.now(), p)}>دیدن فهرست به‌روز</button>
    </div>
  )
}
