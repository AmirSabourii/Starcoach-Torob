// Reusable calm mini-map: MapLibre GL + OpenFreeMap «positron» vector style (OpenMapTiles schema, no key), custom HTML pins.
// Falls back to Leaflet + OSM raster tiles if the vector style/tiles do not load within a few seconds.
// Props are generic (pins[], onPinClick) so a later step can let the shopper tap a pin and talk about it.
import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import L from 'leaflet'

export type MapPin = { id: string; lat: number; lon: number; kind: 'user' | 'shop' | 'bazaar' | 'closed'; label?: string }
const STYLE = 'https://tiles.openfreemap.org/styles/positron'
let rtlSet = false
/** Persian labels in vector tiles need the RTL shaping plugin (served locally from /app/assets); call before creating any map */
export function ensureRTL() {
  if (rtlSet) return
  rtlSet = true
  try { maplibregl.setRTLTextPlugin(new URL('assets/mapbox-gl-rtl-text.js', document.baseURI).href, true) } catch { /* already set */ }
}
export const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'

function pinEl(p: MapPin, onClick?: (p: MapPin) => void) {
  const el = document.createElement('div')
  el.className = 'mm-pin mm-' + p.kind
  el.innerHTML = p.kind === 'user' ? '<i></i>'
    : p.kind === 'bazaar' ? `<i></i>${p.label ? `<span>${p.label.replace(/</g, '')}</span>` : ''}`
    : `<svg width="26" height="32" viewBox="0 0 26 32" aria-hidden="true"><path d="M13 31s10-10.2 10-18A10 10 0 0 0 3 13c0 7.8 10 18 10 18z"/><circle cx="13" cy="13" r="4" fill="#fff"/></svg>`
  if (p.label) el.title = p.label
  if (onClick) { el.style.cursor = 'pointer'; el.addEventListener('click', (e) => { e.stopPropagation(); onClick(p) }) }
  return el
}

export function MiniMap({ pins, onPinClick, height = 170 }: { pins: MapPin[]; onPinClick?: (p: MapPin) => void; height?: number }) {
  const box = useRef<HTMLDivElement>(null)
  const [engine, setEngine] = useState<'vector' | 'raster'>('vector')
  const key = pins.map((p) => `${p.id}:${p.lat.toFixed(5)},${p.lon.toFixed(5)}`).join('|')
  useEffect(() => {
    const el = box.current
    if (!el || !pins.length) return
    const lats = pins.map((p) => p.lat), lons = pins.map((p) => p.lon)
    const sw: [number, number] = [Math.min(...lons), Math.min(...lats)], ne: [number, number] = [Math.max(...lons), Math.max(...lats)]
    if (engine === 'raster') {
      const m = L.map(el, { zoomControl: false, attributionControl: true, scrollWheelZoom: false })
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(m)
      m.attributionControl.setPrefix(false)
      pins.forEach((p) => L.marker([p.lat, p.lon], { icon: L.divIcon({ className: '', html: pinEl(p).outerHTML, iconSize: [26, 32], iconAnchor: p.kind === 'shop' || p.kind === 'closed' ? [13, 31] : [9, 9] }) })
        .on('click', () => onPinClick?.(p)).addTo(m))
      m.fitBounds([[sw[1], sw[0]], [ne[1], ne[0]]], { padding: [34, 34], maxZoom: 15 })
      return () => { m.remove() }
    }
    ensureRTL()
    let loaded = false
    const map = new maplibregl.Map({ container: el, style: STYLE, bounds: [sw, ne], fitBoundsOptions: { padding: { top: 36, bottom: 30, left: 70, right: 70 }, maxZoom: 15 }, attributionControl: false,
      cooperativeGestures: true, dragRotate: false, pitchWithRotate: false, touchPitch: false, locale: {
        'CooperativeGesturesHandler.WindowsHelpText': 'برای بزرگ‌نمایی Ctrl را نگه دارید و اسکرول کنید', 'CooperativeGesturesHandler.MacHelpText': 'برای بزرگ‌نمایی ⌘ را نگه دارید و اسکرول کنید',
        'CooperativeGesturesHandler.MobileHelpText': 'برای جابه‌جایی نقشه از دو انگشت استفاده کنید' } })
    map.addControl(new maplibregl.AttributionControl({ compact: true }))
    map.once('load', () => el.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show'))   // start collapsed (ⓘ)
    map.touchZoomRotate.disableRotation()
    const markers = pins.map((p) => new maplibregl.Marker({ element: pinEl(p, onPinClick), anchor: p.kind === 'shop' || p.kind === 'closed' ? 'bottom' : 'center' }).setLngLat([p.lon, p.lat]).addTo(map))
    map.on('load', () => { loaded = true })
    const tm = window.setTimeout(() => { if (!loaded) setEngine('raster') }, 6000)     // style/tiles blocked -> raster fallback
    map.on('error', (e) => { if (!loaded && /style|Failed to fetch|tiles/i.test(String(e?.error?.message || ''))) setEngine('raster') })
    const ro = new ResizeObserver(() => map.resize()); ro.observe(el)
    return () => { window.clearTimeout(tm); ro.disconnect(); markers.forEach((m) => m.remove()); map.remove() }
  }, [key, engine])      // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={box} className={'mm ' + engine} style={{ height }} data-engine={engine} />
}
