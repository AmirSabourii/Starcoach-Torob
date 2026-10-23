import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api, errText } from './api'
import { fa } from './fmt'
import { Spinner } from './ui'

type Shop = { shop_id: string; name: string; area: string; lat: number; lon: number; nearby: string }
type Resp = { centre: [number, number]; shops: Shop[]; n_total_in_view: number; filter: string | null }
const TILES: [string, string][] = [['', 'همه'], ['digital', 'کالای دیجیتال'], ['home', 'خانه و آشپزخانه'], ['fashion', 'مد و پوشاک'], ['sport', 'ورزش و سفر'],
  ['beauty', 'زیبایی و سلامت'], ['kids', 'اسباب‌بازی و کودک'], ['books', 'کتاب و لوازم تحریر'], ['tools', 'ابزار و ساختمان']]

const pinIcon = (n?: number) => L.divIcon({ className: 'lf-pin', html: `<span>${n ? fa(n) : ''}</span>`, iconSize: [26, 34], iconAnchor: [13, 32] })
const meIcon = L.divIcon({ className: 'lf-me', html: '<span></span>', iconSize: [18, 18], iconAnchor: [9, 9] })

/** small reusable Leaflet map: pins → onPin(shop_id) */
export function LeafletPins({ centre, pins, onPin, numbered, zoom = 13, className = '' }: {
  centre: [number, number] | null; pins: { shop_id: string; name: string; lat: number; lon: number }[]; onPin?: (sid: string) => void
  numbered?: boolean; zoom?: number; className?: string
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  useEffect(() => {
    if (!el.current) return
    const m = L.map(el.current, { zoomControl: false, attributionControl: true })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(m)
    m.attributionControl.setPrefix(false)
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = null }
  }, [])
  useEffect(() => {
    const m = map.current, g = layer.current
    if (!m || !g) return
    g.clearLayers()
    const pts: L.LatLngExpression[] = []
    if (centre) { L.marker(centre, { icon: meIcon, interactive: false }).addTo(g); pts.push(centre) }
    pins.forEach((p, i) => {
      if (p.lat == null || p.lon == null) return
      const mk = L.marker([p.lat, p.lon], { icon: pinIcon(numbered ? i + 1 : undefined), title: p.name }).addTo(g)
      mk.bindTooltip(p.name, { direction: 'top', offset: [0, -30] })
      if (onPin) mk.on('click', () => onPin(p.shop_id))
      pts.push([p.lat, p.lon])
    })
    if (pts.length > 1) m.fitBounds(L.latLngBounds(pts), { padding: [28, 28], maxZoom: 15 })
    else if (pts.length === 1) m.setView(pts[0], zoom)
    else m.setView([35.715, 51.404], 11)
  }, [centre, pins, numbered, onPin, zoom])
  return <div ref={el} className={'lf ' + className} />
}

export function MapTab({ area, areaLabel, onShop, onArea, initialTile, query }: {
  area: string; areaLabel: string; onShop: (sid: string) => void; onArea: () => void; initialTile?: string; query?: string
}) {
  const [tile, setTile] = useState(initialTile || '')
  const [q, setQ] = useState(query || '')
  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let alive = true
    setLoading(true); setErr(null)
    const qs = new URLSearchParams({ area, limit: '60' })
    if (tile) qs.set('tile', tile); else if (q) qs.set('q', q)
    api<Resp>('/api/home/shops?' + qs.toString())
      .then((r) => { if (alive) setData(r) })
      .catch((e) => { if (alive) setErr(errText(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [area, tile, q])
  const near = data ? data.shops.filter((s) => s.nearby === 'همین نزدیکی').length : 0
  return (
    <div className="maptab">
      <div className="map-filters">
        <button className="loc-chip small" onClick={onArea}><span className="dot-pin" />نزدیک {areaLabel}</button>
        {q && !tile ? <button className="fchip on" onClick={() => setQ('')}>«{q}» ✕</button> : null}
        {TILES.map(([k, l]) => (
          <button key={k || 'all'} className={'fchip' + (tile === k && !(k === '' && q) ? ' on' : '')} onClick={() => { setTile(k); if (k) setQ('') }}>{l}</button>
        ))}
      </div>
      <div className="map-box">
        <LeafletPins centre={data?.centre || null} pins={data?.shops || []} onPin={onShop} />
        {loading && <div className="map-loading"><Spinner /></div>}
      </div>
      <div className="map-foot">
        {err ? <span className="err">{err}</span> : data ? (
          data.shops.length ? <span>{fa(data.shops.length)} فروشگاه روی نقشه{near ? ` · ${fa(near)} تا همین نزدیکی` : ' · نزدیک‌ترین‌ها کمی دورترند'}{data.filter ? ` · ${data.filter}` : ''}</span>
            : <span>این‌جا فروشگاهی برای این فیلتر ثبت نشده؛ محدودهٔ دیگری را امتحان کن.</span>
        ) : null}
      </div>
    </div>
  )
}
