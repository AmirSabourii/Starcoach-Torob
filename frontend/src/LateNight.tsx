// «الان کجا بازه؟» answer block: compact map (you · nearest OPEN shop · nearby bazaar) + calm shop card + bazaar card.
import { useState } from 'react'
import { MiniMap, type MapPin } from './MiniMap'
import { fa, faNum } from './fmt'
import { Pin } from './icons'

type Routes = { google: string; neshan: string } | null
export type LateBlock = {
  type: 'late_night'; now: string; day: string; user: { lat: number; lon: number; label: string }; n_closer_closed: number
  shop: null | { shop_id: string; name: string; place: string; lat: number; lon: number; distance_label: string | null; until: string | null; until_fa: string
    product_id: string; product_title: string; price_toman: number; same_product: boolean; location: string | null; routes: Routes }
  bazaar: null | { name: string; lat: number; lon: number; distance_label: string | null; hours_label: string; routes: Routes }
  next_open?: { shop_id: string; name: string; when: string; opens_at: string; distance_label: string | null }
}

function Route({ routes }: { routes: Routes }) {
  const [open, setOpen] = useState(false)
  if (!routes) return null
  return open
    ? <span className="ln-route"><a href={routes.neshan} target="_blank" rel="noreferrer">نشان</a><i>·</i><a href={routes.google} target="_blank" rel="noreferrer">گوگل‌مپ</a></span>
    : <button className="ln-act" onClick={(e) => { e.stopPropagation(); setOpen(true) }}>مسیریابی</button>
}

export function LateNight({ b, onShop }: { b: LateBlock; onShop: (sid: string, pid?: string) => void }) {
  const pins: MapPin[] = [{ id: 'user', kind: 'user', lat: b.user.lat, lon: b.user.lon, label: 'شما' }]
  if (b.shop) pins.push({ id: b.shop.shop_id, kind: 'shop', lat: b.shop.lat, lon: b.shop.lon, label: b.shop.name })
  if (b.bazaar) pins.push({ id: 'bazaar', kind: 'bazaar', lat: b.bazaar.lat, lon: b.bazaar.lon, label: 'بازار ' + b.bazaar.name.replace(/\s*\(.*\)/, '') })
  const s = b.shop
  return (
    <div className="ln">
      <MiniMap pins={pins} onPinClick={(p) => { if (s && p.id === s.shop_id) onShop(s.shop_id, s.product_id) }} />
      {s ? (
        <div className="ln-card" role="button" onClick={() => onShop(s.shop_id, s.product_id)}>
          <div className="ln-top"><b>{s.name}</b><Route routes={s.routes} /></div>
          <div className="ln-line"><Pin size={13} color="#9a9bab" /> {s.place}{s.distance_label ? ' · ' + s.distance_label : ''}</div>
          <div className="ln-open"><i /> الان باز تا {s.until_fa}</div>
          <div className="ln-price"><span className="ln-pt">{s.same_product ? 'همین محصول' : s.product_title}</span><b>{faNum(s.price_toman)} <small>تومان</small></b></div>
        </div>
      ) : b.next_open ? (
        <div className="ln-card">
          <div className="ln-top"><b>{b.next_open.name}</b></div>
          <div className="ln-line">{b.next_open.distance_label || ''}</div>
          <div className="ln-open closed"><i /> {b.next_open.when} از {fa(b.next_open.opens_at)} باز می‌کنه</div>
        </div>
      ) : null}
      {b.bazaar ? (
        <div className="ln-card soft">
          <div className="ln-top"><b>بازار {b.bazaar.name}</b><Route routes={b.bazaar.routes} /></div>
          <div className="ln-line">{b.bazaar.distance_label ? b.bazaar.distance_label + ' · ' : ''}ساعت کاری {b.bazaar.hours_label}</div>
          <div className="ln-note">ممکنه مغازه‌هایی که تو ترب نیستن هنوز باز باشن</div>
        </div>
      ) : null}
    </div>
  )
}
