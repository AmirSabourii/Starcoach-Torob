// Product page: summary (hero gallery + AI summary from /about cited) · sellers (real filters) · specs. Full-screen layer.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, CID, errText, SID } from './api'
import { fa, faNum, milNum, milRange, short, splitTitle, UNKNOWN } from './fmt'
import { BackIcon, ChevLeft, Heart, MapIcon, Pin, SparkFill } from './icons'
import { Img, MascotAvatar, Sheet } from './ui'
import { CatTile } from './catIcon'
import { LeafletPins } from './MapView'
import { StatusBar } from './StatusBar'
import { TryOnEntry } from './tryon/TryOn'

export type Seller = {
  offer_id: string; shop_id: string; shop_name: string; shop_area: string; place: string; place_is_bazaar: boolean
  shop_lat: number | null; shop_lon: number | null; price_toman: number | null; price_note: string | null; date_fa: string; age_days: number | null
  stale: boolean; suspicious: boolean; labels: string[]; fast_delivery: boolean | null; installment: boolean; installment_providers: string[]
  warranty_info: { has: boolean; months: number | null; label: string | null }; distance_label: string | null; near_rank?: number
  updated_fa: string; main_category: string | null; cheapest?: boolean; open_state?: string | null; open_badge?: string | null
}
export type SellersR = { product_id: string; title: string; model: string | null; image: string | null; n_shops: number; min_price: number | null; max_price: number | null
  sellers: Seller[]; counts: { fast: number; installment: number; warranty: number }; places: { n: number; kind: string; together: boolean } }
type Details = { images: string[]; specs: { section: string; items: { key: string; value: string }[] }[] }
type About = { sentences: string[]; cited: { text: string; refs: number[] }[]; sources: { n: number; title: string; url: string }[] }
type Tab = 'summary' | 'sellers' | 'specs'

/** sentence + its citation numbers glued to the last word (never wraps onto its own line); each number opens its source */
function Cited({ rows, sources }: { rows: { text: string; refs: number[] }[]; sources: About['sources'] }) {
  return <>{rows.map((c, i) => {
    const t = c.text.trim()
    const refs = (c.refs || []).filter((n) => sources.some((x) => x.n === n))
    if (!refs.length) return <span key={i}>{t} </span>
    const k = t.lastIndexOf(' ')
    return <span key={i}>{k > 0 ? t.slice(0, k + 1) : ''}<span className="nw">{k > 0 ? t.slice(k + 1) : t}{refs.map((n) => {
      const src = sources.find((x) => x.n === n)!
      return <a key={n} className="cite" href={src.url} target="_blank" rel="noreferrer" title={src.title}>{fa(n)}</a>
    })}</span> </span>
  })}</>
}

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const idx = { summary: 0, sellers: 1, specs: 2 }[tab]
  return (
    <div className="ptabs" role="tablist">
      <span className="ptabs-pill" style={{ transform: `translateX(${-idx * 100}%)` }} aria-hidden />
      <button role="tab" aria-selected={tab === 'summary'} onClick={() => setTab('summary')}>خلاصه</button>
      <button role="tab" aria-selected={tab === 'sellers'} onClick={() => setTab('sellers')}>فروشنده‌ها</button>
      <button role="tab" aria-selected={tab === 'specs'} onClick={() => setTab('specs')}>مشخصات</button>
    </div>
  )
}

function SellerCard({ s, onOpen, near }: { s: Seller; onOpen: () => void; near: boolean }) {
  const tags = [s.warranty_info?.has ? s.warranty_info.label : null, s.fast_delivery ? 'ارسال سریع' : null, s.installment ? 'قسطی' : null].filter(Boolean) as string[]
  return (
    <button className="scard" onClick={onOpen}>
      <div className="scard-top">
        <CatTile name={s.main_category} size={44} radius={14} icon={21} />
        <div className="scard-c">
          <div className="scard-n"><b>{s.shop_name}</b>{s.cheapest ? <span className="pill-green">ارزان‌ترین</span> : null}</div>
          <div className="scard-a"><Pin size={12} color="#8d8ea0" /> {s.place}{near && s.distance_label ? <em> · {s.distance_label}</em> : null}
            {s.open_badge ? <i className={'cs-dot ' + (s.open_state === 'open' ? 'on' : 'off')} title={s.open_badge} aria-label={s.open_badge} /> : null}</div>
        </div>
        <div className="scard-p">{s.price_toman ? <><b>{faNum(s.price_toman)}</b><small>تومان</small></> : <b className="unk">{UNKNOWN}</b>}</div>
        <span className="chev-c"><ChevLeft size={9} /></span>
      </div>
      <div className="scard-b">
        <div className="tags">{tags.map((t) => <span key={t}>{t}</span>)}</div>
        {s.open_state === 'closed_now' || s.open_state === 'closed_today' ? <span className="cs-link xs">جایگزین باز ←</span> : null}
        {s.suspicious ? <span className="badge-red">قیمت مشکوک</span> : s.stale ? <span className="badge-amber">قیمت قدیمی</span> : <small>{s.updated_fa}</small>}
      </div>
    </button>
  )
}

export function ProductPage({ pid, tab0 = 'summary', area, areaLabel, sbar, onClose, onShop, toast }: {
  pid: string; tab0?: Tab; area: string; areaLabel: string; sbar: boolean; onClose: () => void; onShop: (sid: string, pid: string, alt?: boolean) => void; toast: (t: string) => void
}) {
  const [tab, setTab] = useState<Tab>(tab0)
  const [s, setS] = useState<SellersR | null>(null)
  const [d, setD] = useState<Details | null>(null)
  const [about, setAbout] = useState<About | null | 'none'>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sort, setSort] = useState<'cheap' | 'near'>('cheap')
  const [flt, setFlt] = useState<{ fast?: boolean; inst?: boolean; warr?: boolean }>({})
  const [img, setImg] = useState(0)
  const [saved, setSaved] = useState(false)
  const [map, setMap] = useState(false)
  const [tick, setTick] = useState(0)
  const scroll = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let alive = true
    const P = encodeURIComponent(pid)
    setErr(null)
    api<SellersR>(`/api/home/sellers/${P}?area=${encodeURIComponent(area)}`).then((r) => alive && setS(r)).catch((e) => alive && setErr(errText(e)))
    api<Details>(`/api/product/${P}/details`).then((r) => alive && setD(r)).catch(() => {})
    api<About>(`/api/product/${P}/about`, { timeout: 30000, retries: 0 }).then((r) => alive && setAbout(r)).catch(() => alive && setAbout('none'))
    api('/api/memory/select', { body: { sid: SID, version: 'v3plus', kind: 'product', id: pid } }).catch(() => {})
    return () => { alive = false }
  }, [pid, area, tick])
  useEffect(() => { scroll.current?.scrollTo({ top: 0 }) }, [tab])
  const save = async () => {
    try { const r: any = await api('/api/lists/items', { body: { cid: CID, product_id: pid } }); setSaved(true); toast(r.already_saved ? 'قبلاً در «لیست من» بود' : 'به «لیست من» اضافه شد') } catch (e) { toast(errText(e)) }
  }
  const [faT, latin] = splitTitle(s?.title)
  const images = d?.images?.length ? d.images : s?.image ? [s.image] : []
  const list = useMemo(() => {
    if (!s) return []
    let l = s.sellers.filter((x) => (!flt.fast || x.fast_delivery) && (!flt.inst || x.installment) && (!flt.warr || x.warranty_info?.has))
    if (sort === 'near') l = [...l].sort((a, b) => (a.near_rank ?? 1e9) - (b.near_rank ?? 1e9))
    return l
  }, [s, flt, sort])
  const lp = list.filter((x) => x.price_toman && !x.suspicious).map((x) => x.price_toman as number)
  const cheapest = s?.sellers.find((x) => x.cheapest) || null
  const aboutRows = about && about !== 'none' ? (about.cited?.length ? about.cited : (about.sentences || []).map((t) => ({ text: t, refs: [] as number[] }))).filter((c) => c.text && c.text.trim()) : []
  const srcs = about && about !== 'none' ? about.sources || [] : []
  const head = (
    <div className="pp-head">
      <button className="circ" onClick={onClose} aria-label="بازگشت"><BackIcon /></button>
      <span className="pp-thumb"><Img src={s?.image} /></span>
      <div className="pp-ht"><b>{short(faT, 30)}</b>{latin ? <small dir="ltr">{latin}</small> : null}</div>
      <button className="circ" onClick={save} aria-label="ذخیره"><Heart on={saved} /></button>
    </div>
  )
  const chip = (on: boolean, label: string, fn: () => void, n?: number) => <button className={'fchip' + (on ? ' on' : '')} onClick={fn} disabled={n === 0}>{label}</button>
  return (
    <div className="ovl-page">
      {tab !== 'summary' ? <div className="sb-space">{sbar ? <StatusBar /> : null}</div> : null}
      {err ? (
        <><div className="pp-head"><button className="circ" onClick={onClose} aria-label="بازگشت"><BackIcon /></button></div>
          <div className="empty"><MascotAvatar state="think" size={64} /><p>{err}</p><button className="btn-dark" onClick={() => setTick((t) => t + 1)}>تلاش دوباره</button></div></>
      ) : !s ? (
        <div className="empty" style={{ paddingTop: 140 }}><MascotAvatar state="search" size={64} /><p>در حال آوردن اطلاعات…</p></div>
      ) : tab === 'summary' ? (
        <div className="pp-scroll" ref={scroll}>
          <div className="hero">
            {sbar ? <StatusBar /> : null}
            <div className="hero-btns">
              <button className="circ" onClick={onClose} aria-label="بازگشت"><BackIcon /></button>
              <button className="circ" onClick={save} aria-label="ذخیره"><Heart on={saved} /></button>
            </div>
            <div className="hero-gal" onScroll={(e) => { const t = e.currentTarget; setImg(Math.round(Math.abs(t.scrollLeft) / t.clientWidth)) }}>
              {(images.length ? images : [null]).map((u, i) => <div className="hero-i" key={i}><Img src={u} /></div>)}
            </div>
            {images.length > 1 ? <div className="hero-dots">{images.slice(0, 8).map((_, i) => <span key={i} className={i === img ? 'on' : ''} />)}</div> : null}
          </div>
          <div className="pp-body">
            <h1 className="pp-title">{faT}</h1>
            {latin ? <div className="pp-model" dir="ltr">{latin}</div> : null}
            <div className="pp-price">
              <span>{s.min_price ? (s.min_price >= 1e6 ? <>از <b>{milNum(s.min_price)}</b> میلیون تومان</> : <>از <b>{faNum(s.min_price)}</b> تومان</>) : <b className="unk">{UNKNOWN}</b>}</span>
              <button className="pill-grey" onClick={() => setTab('sellers')}>{fa(s.n_shops)} فروشنده</button>
            </div>
            <TryOnEntry product={{ product_id: pid, title: s.title, image: s.image, min_price: s.min_price }} onCompare={() => setTab('sellers')} toast={toast} sbar={sbar} />
            <Tabs tab={tab} setTab={setTab} />
            {aboutRows.length ? (
              <>
                <section className="ai-card">
                  <h3><SparkFill /> خلاصهٔ هوش مصنوعی</h3>
                  <p><Cited rows={aboutRows.slice(0, 2)} sources={srcs} /></p>
                </section>
                {aboutRows.length > 2 ? <p className="pp-desc"><Cited rows={aboutRows.slice(2)} sources={srcs} /></p> : null}
              </>
            ) : about === null ? (
              <section className="ai-card skel" aria-hidden><h3><SparkFill /> خلاصهٔ هوش مصنوعی</h3><i /><i /><i /></section>
            ) : d?.specs?.[0]?.items?.length ? (
              <div className="pp-specs">{d.specs[0].items.slice(0, 5).map((it, j) => <div key={j}><span>{it.key}</span><b>{it.value}</b></div>)}</div>
            ) : null}
            <div style={{ height: 24 }} />
          </div>
        </div>
      ) : tab === 'sellers' ? (
        <>
          {head}
          <div className="pp-tabs-wrap"><Tabs tab={tab} setTab={setTab} /></div>
          <div className="fchips">
            {chip(sort === 'cheap', 'ارزان‌ترین', () => setSort('cheap'))}
            {chip(sort === 'near', 'نزدیک‌ترین', () => setSort('near'))}
            {chip(!!flt.fast, 'ارسال سریع', () => setFlt((f) => ({ ...f, fast: !f.fast })), s.counts.fast)}
            {chip(!!flt.inst, 'قسطی', () => setFlt((f) => ({ ...f, inst: !f.inst })), s.counts.installment)}
            {chip(!!flt.warr, 'با گارانتی', () => setFlt((f) => ({ ...f, warr: !f.warr })), s.counts.warranty)}
          </div>
          <div className="pp-scroll" ref={scroll}>
            <div className="s-count">{fa(list.length)} فروشنده{lp.length ? <> <i>•</i> {milRange(Math.min(...lp), Math.max(...lp))}</> : null}{sort === 'near' ? <> <i>•</i> نزدیک به {areaLabel}</> : null}</div>
            {list.map((x) => <SellerCard key={x.offer_id} s={x} near={sort === 'near'} onOpen={() => onShop(x.shop_id, pid, x.open_state === 'closed_now' || x.open_state === 'closed_today')} />)}
            {!list.length ? <div className="empty small">با این فیلترها فروشنده‌ای نیست.</div> : null}
            <div style={{ height: 24 }} />
          </div>
        </>
      ) : (
        <>
          {head}
          <div className="pp-tabs-wrap"><Tabs tab={tab} setTab={setTab} /></div>
          <div className="pp-scroll" ref={scroll}>
            {d?.specs?.length ? d.specs.map((sec, i) => (
              <section className="spec-card" key={i}><h3>{sec.section || 'مشخصات'}</h3>
                {sec.items.map((it, j) => <div className="spec-r" key={j}><span>{it.key}</span><b>{it.value}</b></div>)}</section>
            )) : <div className="empty small">{d ? 'مشخصاتی ثبت نشده است.' : 'در حال آوردن مشخصات…'}</div>}
            <div style={{ height: 24 }} />
          </div>
        </>
      )}
      {s && tab === 'sellers' ? (
        <div className="pp-foot">
          <button className="btn-ink" onClick={() => setMap(true)}><MapIcon size={18} /> نمایش روی نقشه</button>
          <div className="pp-foot-l"><small>{s.places.together ? 'همه همین نزدیکی' : 'در چند نقطهٔ شهر'}</small><b>{fa(s.places.n)} {s.places.kind}</b></div>
        </div>
      ) : s && tab === 'summary' ? (
        <div className="pp-foot">
          <button className="btn-ink" onClick={() => setTab('sellers')}>مقایسهٔ فروشنده‌ها</button>
          <div className="pp-foot-l"><small>ارزان‌ترین</small><span>{cheapest?.price_toman ? <><b>{faNum(cheapest.price_toman)}</b> تومان</> : <b className="unk">{UNKNOWN}</b>}</span></div>
        </div>
      ) : null}
      {map && s ? (
        <Sheet onClose={() => setMap(false)} className="map-sheet">
          <div className="sheet-t">فروشنده‌های {short(faT, 26)} روی نقشه</div>
          <LeafletPins centre={null} numbered className="pmap" pins={list.filter((x) => x.shop_lat != null).map((x) => ({ shop_id: x.shop_id, name: x.shop_name, lat: x.shop_lat as number, lon: x.shop_lon as number }))}
            onPin={(sid) => { setMap(false); onShop(sid, pid) }} />
        </Sheet>
      ) : null}
    </div>
  )
}
