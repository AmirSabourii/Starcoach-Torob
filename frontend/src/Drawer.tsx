import { useEffect, useState } from 'react'
import { api, CID, errText, SID } from './api'
import { clean, fa, faNum, host, short, stripParen, toman, UNKNOWN } from './fmt'
import { Bookmark, Close, Heart, Store } from './icons'
import { Img, MascotAvatar, Sheet, Spinner } from './ui'
import { LeafletPins } from './MapView'

type Offer = { offer_id: string; shop_id: string; shop_name: string; shop_area: string; price_toman: number | null; date_fa: string; labels: string[]; warranty: string; stale: boolean; suspicious: boolean }
type Offers = { product_id: string; title: string; brand: string; category: string; image: string | null; min_price: number | null; min_fresh_price: number | null; median_price: number | null; n_offers: number; n_shops: number; offers: Offer[] }
type Details = { images: string[]; specs: { section: string; items: { key: string; value: string }[] }[]; n_specs: number; stats: { latest_price_change_fa?: string; max_price?: number | null } }
type About = { sentences: string[]; cited: { text: string; refs: number[] }[]; sources: { n: number; title: string; url: string }[] }
type Related = { product_id: string; title: string; image: string | null; price: { price_toman: number | null; labels: string[] } | null; n_shops: number }
export type Bazaar = { group: string | null; hubs: { name: string; shop_count: number; share_of_group_offers: number; map_url: string; center: [number, number]; evidence_fa: string; shops: { shop_id: string; name: string; area: string; lat: number; lon: number }[] }[] }

const saveItem = (body: Record<string, unknown>) => api('/api/lists/items', { body: { cid: CID, ...body } })

export function BazaarCard({ b, onShop }: { b: Bazaar; onShop: (sid: string) => void }) {
  if (!b || !b.hubs || !b.hubs.length) return null
  return (
    <div className="bz">
      <div className="bz-h">بورس {clean(b.group)}</div>
      {b.hubs.map((h) => (
        <div className="bz-hub" key={h.name}>
          <div className="bz-row"><b>{h.name}</b><a className="bz-map" href={h.map_url} target="_blank" rel="noreferrer">روی نقشه</a></div>
          <div className="bz-bar"><span style={{ width: Math.max(4, Math.round((h.share_of_group_offers || 0) * 100)) + '%' }} /></div>
          <div className="bz-sub">{fa(h.shop_count)} فروشگاه{h.share_of_group_offers ? ` · ${fa(Math.round(h.share_of_group_offers * 100))}٪ پیشنهادهای این گروه` : ''}</div>
          <div className="bz-shops">
            {h.shops.slice(0, 4).map((s) => (
              <button key={s.shop_id} className="bz-shop" onClick={() => onShop(s.shop_id)}><span className="av">{s.name.slice(0, 1)}</span>{s.name}</button>
            ))}
          </div>
        </div>
      ))}
      {b.hubs[0].evidence_fa ? <div className="bz-ev">{b.hubs[0].evidence_fa}</div> : null}
    </div>
  )
}

export function ProductDrawer({ pid, onClose, onShop, onProduct, toast }: { pid: string; onClose: () => void; onShop: (sid: string) => void; onProduct: (pid: string) => void; toast: (t: string) => void }) {
  const [o, setO] = useState<Offers | null>(null)
  const [d, setD] = useState<Details | null>(null)
  const [about, setAbout] = useState<About | null>(null)
  const [rel, setRel] = useState<Related[]>([])
  const [bz, setBz] = useState<Bazaar | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [img, setImg] = useState(0)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setO(null); setD(null); setAbout(null); setRel([]); setBz(null); setErr(null); setAll(false); setImg(0)
    const P = encodeURIComponent(pid)
    Promise.all([api<Offers>(`/api/product/${P}/offers`), api<Details>(`/api/product/${P}/details`)])
      .then(([a, b]) => { if (alive) { setO(a); setD(b) } })
      .catch((e) => alive && setErr(errText(e)))
    api<{ related: Related[] }>(`/api/product/${P}/related?k=8`).then((r) => alive && setRel(r.related || [])).catch(() => {})
    api<Bazaar>(`/api/bazaar?product_id=${P}`).then((r) => alive && setBz(r)).catch(() => {})
    api<About>(`/api/product/${P}/about`, { timeout: 30000, retries: 0 }).then((r) => alive && setAbout(r)).catch(() => {})
    api('/api/memory/select', { body: { sid: SID, version: 'v3plus', kind: 'product', id: pid } }).catch(() => {})
    return () => { alive = false }
  }, [pid, tick])
  const save = async (key: string, body: Record<string, unknown>) => {
    try {
      const r: any = await saveItem(body)
      setSaved((s) => ({ ...s, [key]: true }))
      toast(r.already_saved ? 'قبلاً در «لیست من» بود' : 'به «لیست من» اضافه شد')
    } catch (e) { toast(errText(e)) }
  }
  const images = d?.images?.length ? d.images : o?.image ? [o.image] : []
  const price = o ? (o.min_fresh_price ?? o.min_price) : null
  const offers = o ? (all ? o.offers : o.offers.slice(0, 5)) : []
  const cited = about?.cited?.length ? about.cited : (about?.sentences || []).map((t) => ({ text: t, refs: [] as number[] }))
  return (
    <Sheet onClose={onClose} full className="drawer">
      <div className="dr-top">
        <button className="icon-btn" onClick={() => save('top', { product_id: pid })} aria-label="ذخیره"><Heart on={saved.top} /></button>
        <button className="icon-btn" onClick={onClose} aria-label="بستن"><Close /></button>
      </div>
      <div className="dr-scroll">
        {err ? (
          <div className="empty"><MascotAvatar state="think" size={64} /><p>{err}</p><button className="btn-dark" onClick={() => setTick((t) => t + 1)}>تلاش دوباره</button></div>
        ) : !o ? (
          <div className="empty"><MascotAvatar state="search" size={64} /><p>در حال آوردن اطلاعات…</p></div>
        ) : (
          <>
            <div className="gal" onScroll={(e) => { const t = e.currentTarget; setImg(Math.round(Math.abs(t.scrollLeft) / t.clientWidth)) }}>
              {images.length ? images.map((u, i) => <div className="gal-i" key={i}><Img src={u} /></div>) : <div className="gal-i"><Img src={null} /></div>}
            </div>
            {images.length > 1 && <div className="dots">{images.slice(0, 12).map((_, i) => <span key={i} className={i === img ? 'on' : ''} />)}</div>}
            <div className="dr-chips">
              {o.brand && o.brand !== UNKNOWN ? <span className="chip-s">{clean(o.brand)}</span> : null}
              {o.category && o.category !== UNKNOWN ? <span className="chip-s">{clean(o.category)}</span> : null}
            </div>
            <h2 className="dr-title">{o.title}</h2>
            <div className="dr-price">{price ? <>از {faNum(price)} <small>تومان</small></> : <span className="unk">{UNKNOWN}</span>}</div>
            <div className="dr-chips"><span className="chip-g">{fa(o.n_shops)} فروشنده</span>{d?.stats?.latest_price_change_fa ? <span className="chip-s">آخرین تغییر قیمت: {d.stats.latest_price_change_fa}</span> : null}</div>
            <div className="kv">
              <div><span>کمترین قیمت</span><b>{toman(o.min_price)}</b></div>
              <div><span>کمترین قیمت به‌روز</span><b>{toman(o.min_fresh_price)}</b></div>
              <div><span>قیمت میانه</span><b>{toman(o.median_price)}</b></div>
              <div><span>فروشنده‌ها</span><b>{fa(o.n_shops)}</b><small>{fa(o.n_offers)} پیشنهاد ثبت‌شده</small></div>
            </div>
            {cited.length ? (
              <section className="sec-card">
                <h3>دربارهٔ این محصول</h3>
                <p className="about">{cited.map((c, i) => <span key={i}>{c.text}{c.refs?.length ? <sup>{c.refs.map((n) => `[${fa(n)}]`).join('')}</sup> : null} </span>)}</p>
                <div className="srcs">{about!.sources.map((s) => <a key={s.n} href={s.url} target="_blank" rel="noreferrer">[{fa(s.n)}] {host(s.url)}</a>)}</div>
              </section>
            ) : null}
            <section>
              <h3 className="sec-t">فروشنده‌ها</h3>
              {o.offers.length === 0 ? <div className="empty small">برای این کالا پیشنهادی ثبت نشده است.</div> : null}
              {offers.map((f) => (
                <div className="offer" key={f.offer_id}>
                  <button className="offer-main" onClick={() => onShop(f.shop_id)}>
                    <span className="av"><Store /></span>
                    <span className="offer-col">
                      <b>{f.shop_name}</b>
                      <small>{[f.shop_area !== UNKNOWN ? f.shop_area : null, f.date_fa].filter(Boolean).join(' · ')}</small>
                      {f.warranty && f.warranty !== UNKNOWN ? <small className="warr">{f.warranty}</small> : null}
                    </span>
                    <span className="offer-p">
                      {f.price_toman ? <>{faNum(f.price_toman)} <small>تومان</small></> : <span className="unk">{UNKNOWN}</span>}
                      {f.labels.map((l) => <span key={l} className={'flag ' + (l === 'قدیمی' ? 'stale' : 'sus')}>{l}</span>)}
                    </span>
                  </button>
                  <button className="icon-btn sm" aria-label="ذخیره" onClick={() => save(f.offer_id, { product_id: pid, shop_id: f.shop_id, offer_id: f.offer_id })}><Bookmark on={saved[f.offer_id]} /></button>
                </div>
              ))}
              {o.offers.length > 5 && !all ? <button className="link-btn" onClick={() => setAll(true)}>دیدن همهٔ {fa(o.n_offers)} پیشنهاد</button> : null}
            </section>
            {bz && bz.hubs?.length ? <BazaarCard b={bz} onShop={onShop} /> : null}
            {d?.specs?.length ? (
              <section>
                <h3 className="sec-t">مشخصات</h3>
                {d.specs.map((s, i) => (
                  <details className="spec" key={i} open={i === 0}>
                    <summary>{s.section || 'مشخصات'} <small>{fa(s.items.length)}</small></summary>
                    {s.items.map((it, j) => <div className="spec-r" key={j}><span>{it.key}</span><b>{it.value}</b></div>)}
                  </details>
                ))}
              </section>
            ) : null}
            {rel.length ? (
              <section>
                <h3 className="sec-t">محصولات مشابه</h3>
                <div className="hrow">
                  {rel.map((r) => (
                    <button key={r.product_id} className="rcard" onClick={() => onProduct(r.product_id)}>
                      <span className="rcard-im"><Img src={r.image} /></span>
                      <span className="rcard-t">{short(r.title, 44)}</span>
                      <span className="rcard-p">{r.price?.price_toman ? <>{faNum(r.price.price_toman)} <small>تومان</small></> : <span className="unk">{UNKNOWN}</span>}</span>
                      <span className="rcard-s">{fa(r.n_shops)} فروشنده{r.price?.labels?.includes('قدیمی') ? <span className="flag stale">قدیمی</span> : null}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            <div style={{ height: 24 }} />
          </>
        )}
      </div>
    </Sheet>
  )
}

type Shop = { shop_id: string; name: string; address: string; area: string; lat: number | null; lon: number | null; map_url: string | null; hours: { day: string; hours: string; today: boolean }[]; categories: string[]; payment_options: { provider: string; channel: string }[]; fast_delivery: boolean | null; website: string | null; instagram: string | null; phone_display: string | null; phone_note: string | null; n_offers: number; n_products: number; recent_offers: { offer_id: string; product_id: string; title: string; price_toman: number; date_fa: string; labels: string[] }[] }

export function ShopView({ sid, onClose, onProduct }: { sid: string; onClose: () => void; onProduct: (pid: string) => void }) {
  const [s, setS] = useState<Shop | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setS(null); setErr(null)
    api<Shop>(`/api/shop/${encodeURIComponent(sid)}`).then((r) => alive && setS(r)).catch((e) => alive && setErr(errText(e)))
    api('/api/memory/select', { body: { sid: SID, version: 'v3plus', kind: 'shop', id: sid } }).catch(() => {})
    return () => { alive = false }
  }, [sid, tick])
  const today = s?.hours?.find((h) => h.today)
  return (
    <Sheet onClose={onClose} full className="drawer shopv">
      <div className="dr-top">
        <span />
        <button className="icon-btn" onClick={onClose} aria-label="بستن"><Close /></button>
      </div>
      <div className="dr-scroll">
        {err ? (
          <div className="empty"><MascotAvatar state="think" size={64} /><p>{err}</p><button className="btn-dark" onClick={() => setTick((t) => t + 1)}>تلاش دوباره</button></div>
        ) : !s ? (
          <div className="empty"><MascotAvatar state="search" size={64} /><p>در حال آوردن اطلاعات فروشگاه…</p></div>
        ) : (
          <>
            <div className="sh-head">
              <span className="sh-ic"><Store /></span>
              <div><h2>{s.name}</h2><p>{[s.area !== UNKNOWN ? s.area : null, s.address !== UNKNOWN ? s.address : null].filter(Boolean).join('، ')}</p></div>
            </div>
            {s.lat != null && s.lon != null ? (
              <div className="sh-map">
                <LeafletPins centre={null} pins={[{ shop_id: s.shop_id, name: s.name, lat: s.lat, lon: s.lon }]} zoom={15} />
                {s.map_url ? <a className="map-open" href={s.map_url} target="_blank" rel="noreferrer">باز کردن در نقشه</a> : null}
              </div>
            ) : null}
            <div className="dr-chips">
              {today ? <span className="chip-l">امروز: {today.hours}</span> : null}
              {s.fast_delivery ? <span className="chip-g">ارسال سریع</span> : null}
              {s.payment_options.slice(0, 4).map((p, i) => <span key={i} className="chip-o">{p.provider}</span>)}
            </div>
            {s.hours?.length ? (
              <details className="spec"><summary>ساعت کاری</summary>{s.hours.map((h) => <div className="spec-r" key={h.day}><span>{h.day}</span><b>{h.hours}</b></div>)}</details>
            ) : null}
            <div className="sh-info">
              {s.website ? <div><span>وب‌سایت</span><b dir="ltr">{host(s.website)}</b></div> : null}
              {s.instagram ? <div><span>اینستاگرام</span><b dir="ltr">{s.instagram}</b></div> : null}
              {s.phone_display ? <div><span>تلفن</span><b dir="ltr">{fa(s.phone_display)}</b><small>{s.phone_note}</small></div> : null}
              <div><span>پیشنهادهای ثبت‌شده</span><b>{fa(s.n_offers)} پیشنهاد · {fa(s.n_products)} کالا</b></div>
            </div>
            {s.categories?.length ? <div className="dr-chips wrap">{s.categories.slice(0, 8).map((c) => <span key={c} className="chip-s">{clean(c)}</span>)}</div> : null}
            {s.recent_offers?.length ? (
              <section>
                <h3 className="sec-t">تازه‌ترین پیشنهادها</h3>
                <div className="grid2">
                  {s.recent_offers.map((r) => (
                    <button key={r.offer_id} className="rcard g" onClick={() => onProduct(r.product_id)}>
                      <span className="rcard-t">{short(r.title, 54)}</span>
                      <span className="rcard-p">{faNum(r.price_toman)} <small>تومان</small></span>
                      <span className="rcard-s">{r.date_fa}{r.labels.map((l) => <span key={l} className={'flag ' + (l === 'قدیمی' ? 'stale' : 'sus')}>{l}</span>)}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            <div style={{ height: 24 }} />
          </>
        )}
      </div>
    </Sheet>
  )
}
export { stripParen }
