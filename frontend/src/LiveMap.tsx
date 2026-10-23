// Interactive home map: MapLibre + OpenFreeMap positron, DB-only endpoints (/api/map/*, $0). Falls back to the Leaflet MapTab if MapLibre fails.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Map as MLMap, Marker as MLMarker } from 'maplibre-gl'
import { api, SID } from './api'
import { faNum } from './fmt'
import { MapTab } from './MapView'

type Pin = { shop_id: string; name: string; lat: number; lon: number; price_from: number | null; arrive: 'open' | 'closed' | 'unknown' | string
  arrive_label: string; eta_label: string; routes?: { google?: string; neshan?: string }; sells?: string }
type Mode = 'metro' | 'car' | 'walk'
const MODES: [Mode, string][] = [['metro', 'مترو'], ['car', 'ماشین'], ['walk', 'پیاده']]
const HOODS: [string, string][] = [['ونک', 'ونک'], ['تجریش', 'تجریش'], ['انقلاب', 'انقلاب']]
const STYLE = 'https://tiles.openfreemap.org/styles/positron'
const OB_KEY = 'map.onboard'
type Onb = { area: string; label: string; lat: number; lon: number; mode: Mode }

const statusText = (p: Pin) => (p.arrive === 'open' ? 'تا برسی بازه' : p.arrive === 'closed' ? 'بسته‌ست' : 'ساعت کاری نامشخص')
const modeLabel = (m: Mode) => MODES.find((x) => x[0] === m)?.[1] || 'مترو'

function loadOnb(): Onb | null { try { const v = JSON.parse(localStorage.getItem(OB_KEY) || 'null'); return v && typeof v.lat === 'number' ? v : null } catch { return null } }

export function LiveMap({ area, areaLabel, onShop, onArea, onAsk, onAskShop }: {
  area: string; areaLabel: string; onShop: (sid: string) => void; onArea: () => void; onAsk: (q: string) => void; onAskShop: (sid: string, name: string) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<MLMap | null>(null)
  const ml = useRef<typeof import('maplibre-gl') | null>(null)
  const markers = useRef<MLMarker[]>([])
  const pickNext = useRef(false)
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const [onb, setOnb] = useState<Onb | null>(loadOnb)
  const [step, setStep] = useState<0 | 1 | 2>(() => (loadOnb() || localStorage.getItem(OB_KEY + '.later') ? 0 : 1))
  const [hoods, setHoods] = useState<{ key: string; label: string; lat: number; lon: number }[]>([])
  const [pins, setPins] = useState<Pin[]>([])
  const [sel, setSel] = useState<Pin | null>(null)
  const [here, setHere] = useState<{ subtitle: string; place: string | null; shops: Pin[] } | null>(null)
  const [onlyOpen, setOnlyOpen] = useState(false)
  const [q, setQ] = useState('')
  const [reply, setReply] = useState<{ u: string; a: string } | null>(null)
  const mode: Mode = onb?.mode || 'metro'
  const centre = useCallback((): [number, number] => {
    if (onb) return [onb.lat, onb.lon]
    const h = hoods.find((x) => x.key === area || x.label === areaLabel)
    return h ? [h.lat, h.lon] : [35.757, 51.41]
  }, [onb, hoods, area, areaLabel])

  useEffect(() => { api<{ hoods: any[] }>('/api/map/hoods').then((r) => setHoods(r.hoods || [])).catch(() => {}) }, [])

  // MapLibre init (lazy import); any failure -> Leaflet fallback
  useEffect(() => {
    let alive = true, m: MLMap | null = null
    const t = window.setTimeout(() => { if (alive && !map.current?.isStyleLoaded()) setFailed(true) }, 12000)
    ;(async () => {
      try {
        const mod = await import('maplibre-gl')
        await import('maplibre-gl/dist/maplibre-gl.css')
        const maplibregl: any = (mod as any).default || mod
        if (!alive || !el.current) return
        ml.current = maplibregl
        try { if (maplibregl.getRTLTextPluginStatus?.() === 'unavailable') maplibregl.setRTLTextPlugin('https://unpkg.com/@mapbox/mapbox-gl-rtl-text@0.3.0/dist/mapbox-gl-rtl-text.js', true) } catch { /* labels still render */ }
        const [la, lo] = centre()
        m = new maplibregl.Map({ container: el.current, style: STYLE, center: [lo, la], zoom: 13, attributionControl: { compact: true } })
        map.current = m
        m!.on('load', () => { if (alive) setReady(true) })
        m!.on('error', (e: any) => { if (!m!.isStyleLoaded() && String(e?.error?.message || '').match(/style|Failed to fetch/i)) setFailed(true) })
      } catch { if (alive) setFailed(true) }
    })()
    return () => { alive = false; window.clearTimeout(t); markers.current.forEach((x) => x.remove()); m?.remove(); map.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // tap on the map: close the mini-card, else «اینجا چی داره؟» (or pick the start point after «روی نقشه»)
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const onClick = (e: any) => {
      const { lat, lng } = e.lngLat
      if (pickNext.current) {
        pickNext.current = false
        const o: Onb = { area: 'نقطهٔ انتخابی', label: 'نقطهٔ انتخابی', lat, lon: lng, mode }
        setOnb(o); localStorage.setItem(OB_KEY, JSON.stringify(o)); setStep(2); return
      }
      if (sel) { setSel(null); return }
      if (here) { setHere(null); return }
      const [ula, ulo] = centre()
      api<any>('/api/map/here', { body: { lat, lon: lng, ulat: ula, ulon: ulo, sid: SID, mode } })
        .then((r) => setHere({ subtitle: r.subtitle || 'سه مغازهٔ نزدیک این نقطه', place: r.point?.place || null, shops: r.shops || [] }))
        .catch(() => setHere({ subtitle: 'الان در دسترس نیست؛ دوباره امتحان کن.', place: null, shops: [] }))
    }
    m.on('click', onClick)
    return () => { m.off('click', onClick) }
  }, [ready, sel, here, mode, centre])

  // pins
  useEffect(() => {
    if (!ready) return
    const [la, lo] = centre()
    const qs = new URLSearchParams({ sid: SID, lat: String(la), lon: String(lo), mode })
    if (onlyOpen) qs.set('only_open', '1')
    let alive = true
    api<{ pins: Pin[] }>('/api/map/pins?' + qs.toString()).then((r) => { if (alive) setPins(r.pins || []) }).catch(() => { if (alive) setPins([]) })
    return () => { alive = false }
  }, [ready, onb, mode, onlyOpen, centre])

  useEffect(() => {
    const m = map.current, L = ml.current as any
    if (!m || !L || !ready) return
    markers.current.forEach((x) => x.remove()); markers.current = []
    const [la, lo] = centre()
    const me = document.createElement('div'); me.className = 'lm-me'
    markers.current.push(new L.Marker({ element: me }).setLngLat([lo, la]).addTo(m))
    pins.forEach((p) => {
      if (p.lat == null || p.lon == null) return
      const d = document.createElement('button')
      const open = p.arrive === 'open'
      d.className = (open ? 'lm-pin' : 'lm-dot') + (sel?.shop_id === p.shop_id ? ' sel' : '')
      d.setAttribute('aria-label', p.name)
      d.onclick = (ev) => { ev.stopPropagation(); setHere(null); setSel(p) }
      markers.current.push(new L.Marker({ element: d, anchor: open ? 'bottom' : 'center' }).setLngLat([p.lon, p.lat]).addTo(m))
    })
  }, [pins, sel, ready, centre])

  useEffect(() => {     // frame the shopper's point + the pins once per pin load
    const m = map.current, L = ml.current as any
    if (!m || !L || !ready || !pins.length) return
    const [la, lo] = centre()
    const b = new L.LngLatBounds([lo, la], [lo, la])
    pins.forEach((p) => { if (p.lat != null && p.lon != null) b.extend([p.lon, p.lat]) })
    m.fitBounds(b, { padding: { top: 90, bottom: 220, left: 40, right: 40 }, maxZoom: 15, duration: 400 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pins, ready])

  const chooseHood = (k: string, label: string, lat: number, lon: number) => {
    const o: Onb = { area: k, label, lat, lon, mode }
    setOnb(o); localStorage.setItem(OB_KEY, JSON.stringify(o)); setStep(2)
  }
  const pickHood = (k: string) => {
    const h = hoods.find((x) => x.key === k || x.label === k)
    if (h) chooseHood(h.key, h.label, h.lat, h.lon)
  }
  const myLocation = () => {
    if (!navigator.geolocation) { pickHood('ونک'); return }
    navigator.geolocation.getCurrentPosition((p) => chooseHood('me', 'موقعیت فعلی', p.coords.latitude, p.coords.longitude), () => pickHood('ونک'), { timeout: 8000 })
  }
  const setMode = (md: Mode) => {
    const [la, lo] = centre()
    const o: Onb = { ...(onb || { area: area, label: areaLabel, lat: la, lon: lo }), mode: md }
    setOnb(o); localStorage.setItem(OB_KEY, JSON.stringify(o)); setStep(0)
  }
  const sendCmd = async () => {
    const t = q.trim(); if (!t) return
    setQ('')
    const [la, lo] = centre()
    try {
      const r = await api<any>('/api/map/command', { body: { sid: SID, message: t, travel: { mode, lat: la, lon: lo } } })
      if (r.pin) { setOnlyOpen(!!r.filter?.only_open); setReply({ u: t, a: r.text }); return }
    } catch { /* fall through to chat */ }
    onAsk(t)
  }
  const clearFilter = () => { setOnlyOpen(false); setReply(null); api('/api/map/filter', { body: { sid: SID, filter: {} } }).catch(() => {}) }

  if (failed) return <MapTab area={area} areaLabel={areaLabel} onShop={onShop} onArea={onArea} />
  const route = sel?.routes?.neshan || sel?.routes?.google
  return (
    <div className="lm">
      <div ref={el} className="lm-map" />
      <div className="lm-top">
        <button className="lm-chip" onClick={() => setStep(1)}><span className="lm-chip-dot" />{onb?.label || areaLabel}</button>
        <button className="lm-chip" onClick={() => setStep(2)}>{modeLabel(mode)}</button>
      </div>
      {onlyOpen ? <div className="lm-pill">فقط بازها <button aria-label="برداشتن فیلتر" onClick={clearFilter}>✕</button></div> : null}
      {reply ? <div className="lm-reply"><div className="lm-bub">{reply.u}</div><div className="lm-ans">{reply.a}</div></div> : null}

      {step === 1 ? (
        <div className="lm-sheet">
          <div className="lm-grab" />
          <h2>کدوم محله‌ای؟</h2>
          <p>مغازه‌های نزدیکت رو روی نقشه نشون می‌دم.</p>
          <div className="lm-chips">
            <button className="lm-c" onClick={myLocation}>موقعیت فعلی‌ام</button>
            {HOODS.map(([k, l]) => <button key={k} className={'lm-c' + (onb?.area === k ? ' on' : '')} onClick={() => pickHood(k)}>{l}</button>)}
            <button className="lm-c" onClick={() => { pickNext.current = true; setStep(0) }}>روی نقشه</button>
          </div>
          <button className="lm-later" onClick={() => { localStorage.setItem(OB_KEY + '.later', '1'); setStep(0) }}>بعداً</button>
        </div>
      ) : step === 2 ? (
        <div className="lm-sheet">
          <div className="lm-grab" />
          <h2>چطوری میای؟</h2>
          <p>زمان رسیدن رو با همین حساب می‌کنم.</p>
          <div className="lm-chips">{MODES.map(([k, l]) => <button key={k} className={'lm-c' + (mode === k ? ' on' : '')} onClick={() => setMode(k)}>{l}</button>)}</div>
          <button className="lm-later" onClick={() => setStep(0)}>بعداً</button>
        </div>
      ) : sel ? (
        <div className="lm-sheet lm-card">
          <div className="lm-row1"><b>{sel.name}</b>{sel.price_from ? <span className="lm-price"><small>از</small> {faNum(sel.price_from)} <small>تومان</small></span> : null}</div>
          <div className="lm-row2"><span className={'lm-sd' + (sel.arrive === 'open' ? ' on' : '')} />{statusText(sel)}<span className="lm-sep">·</span>{sel.eta_label} با {modeLabel(mode)}</div>
          <div className="lm-acts">
            <button className="lm-primary" onClick={() => onAskShop(sel.shop_id, sel.name)}>دربارهٔ این مغازه بپرس</button>
            {route ? <a className="lm-route" href={route} target="_blank" rel="noreferrer" aria-label="مسیریابی">➤</a> : null}
            <button className="lm-route" aria-label="صفحهٔ مغازه" onClick={() => onShop(sel.shop_id)}>ⓘ</button>
          </div>
        </div>
      ) : here ? (
        <div className="lm-sheet lm-here">
          <div className="lm-grab" />
          <h2>اینجا چی داره؟</h2>
          <p>{here.place && here.place !== 'نامشخص' ? here.place + ' · ' : ''}{here.subtitle}</p>
          {here.shops.slice(0, 3).map((p) => (
            <button key={p.shop_id} className="lm-item" onClick={() => { setHere(null); setSel(p) }}>
              <b>{p.name}</b>
              <span><span className={'lm-sd' + (p.arrive === 'open' ? ' on' : '')} />{statusText(p)} · {p.eta_label}</span>
              {p.sells ? <small>{p.sells}</small> : null}
            </button>
          ))}
        </div>
      ) : (
        <form className="lm-composer" onSubmit={(e) => { e.preventDefault(); sendCmd() }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="از نقشه بپرس…" />
          <button type="submit" aria-label="ارسال">↑</button>
        </form>
      )}
    </div>
  )
}
