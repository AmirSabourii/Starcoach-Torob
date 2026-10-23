/**
 * «راهنمای رسیدن داخل پاساژ»: Instagram-story-style wayfinding to a shop INSIDE a mall.
 * Spec: /workspace/torob/ux_handoff/spec-mall.md (mall-0 … mall-5 mocks). Data: GET /api/shop/{sid}/mallguide (DB address only)
 * + POST …/mallguide/facts (one cited web lookup per mall, cached). Nothing here is invented: missing floor → no floor step,
 * missing unit → «ask the info desk» step, neighbour unit boxes are blank (no fake numbers), lifts only when a cited page says so.
 *
 *   <MallGuide sid pid sbar onAsk onContact />   entry row (renders nothing when the shop is not in a mall) + the story overlay
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fa } from '../fmt'
import { StatusBar } from '../StatusBar'
import avatar from '../assets/m-avatar.png'
import waveBody from '../mascot3d/assets/wave-body.webp'
import waveLeaves from '../mascot3d/assets/wave-leaves.webp'
import idleBody from '../mascot3d/assets/idle-body.webp'
import idleLeaves from '../mascot3d/assets/idle-leaves.webp'
import searchBody from '../mascot3d/assets/search-body.webp'
import searchLeaves from '../mascot3d/assets/search-leaves.webp'
import foundBody from '../mascot3d/assets/found-body.webp'
import foundLeaves from '../mascot3d/assets/found-leaves.webp'
import { getGuide, getGuideWithFacts, type Guide, type Step } from './mallguideApi'
import './mallguide.css'

const POSE = { wave: [waveBody, waveLeaves], idle: [idleBody, idleLeaves], search: [searchBody, searchLeaves], found: [foundBody, foundLeaves] } as const
type Pose = keyof typeof POSE
const AUTO_MS = 6000

function Mascot({ pose, size, className = '' }: { pose: Pose; size: number; className?: string }) {
  const [b, l] = POSE[pose]
  return (
    <span className={'mg-mascot ' + className} style={{ width: size, height: size }} aria-hidden>
      <img src={b} alt="" draggable={false} /><img className="mg-leaves" src={l} alt="" draggable={false} />
    </span>
  )
}

const Close = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M2 2l10 10M12 2 2 12" /></svg>
const Chev = () => <svg width="8" height="13" viewBox="0 0 8 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6.5 1.5 1.5 6.5l5 5" /></svg>
const FloorsIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="#e6395c" strokeWidth="1.8" strokeLinejoin="round">
    <rect x="4" y="2.5" width="14" height="5" rx="1.6" /><rect x="4" y="8.5" width="14" height="5" rx="1.6" fill="#e6395c" fillOpacity=".14" /><rect x="4" y="14.5" width="14" height="5" rx="1.6" />
  </svg>
)
const Nav = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M20.5 3.5 3.5 10.6l7 2.9 2.9 7 7.1-17Z" /></svg>

/* ------------------------------------------------------------------ entry row (shop sheet) */
export function MallGuideEntry({ guide, onOpen }: { guide: Guide; onOpen: () => void }) {
  if (!guide.eligible || !guide.steps.length) return null
  return (
    <button className="mg-entry" onClick={onOpen}>
      <span className="mg-entry-ic"><FloorsIcon /></span>
      <span className="mg-entry-c"><b>{guide.entry?.title || 'راهنمای رسیدن داخل پاساژ'}</b><small>{guide.entry?.sub || `${fa(guide.steps.length)} مرحلهٔ کوتاه تا جلوی مغازه`}</small></span>
      <span className="mg-entry-chev"><Chev /></span>
    </button>
  )
}

/* ------------------------------------------------------------------ visuals */
const slabLabel = (lv: number) => (lv === 0 ? 'همکف' : lv > 0 ? `طبقهٔ ${fa(lv)}` : `منفی ${fa(-lv)}`)

function Floors({ v }: { v: Extract<Step['visual'], { type: 'floors' }> }) {
  type Row = { k: string; label: string; on?: boolean; ghost?: boolean; gap?: boolean }
  let rows: Row[]
  if (v.target === null || !v.levels) {
    rows = [{ k: 'g1', label: '', ghost: true }, { k: 't', label: v.label, on: true }, { k: 'g2', label: '', ghost: true }]
  } else {
    const L = v.levels
    const pick: (number | 'gap')[] = L.length > 5 ? [L[0], L[1], 'gap', L[L.length - 2], L[L.length - 1]] : L
    rows = [{ k: 'ghost', label: '', ghost: true }, ...pick.map((lv, i): Row => lv === 'gap' ? { k: 'gap' + i, label: '', gap: true }
      : { k: 'l' + lv, label: lv === v.target ? (lv < 0 ? v.label : slabLabel(lv)) : slabLabel(lv), on: lv === v.target })]
  }
  return (
    <div className="mg-floors">
      {rows.map((r) => (
        <div className="mg-frow" key={r.k}>
          <div className={'mg-slab' + (r.on ? ' on' : '') + (r.ghost ? ' ghost' : '') + (r.gap ? ' gap' : '')}>{r.gap ? <i>⋮</i> : r.label}</div>
          <div className="mg-fslot">{r.on ? <Mascot pose="idle" size={74} className="bob" /> : null}</div>
        </div>
      ))}
    </div>
  )
}

function Corridor({ v }: { v: Extract<Step['visual'], { type: 'corridor' }> }) {
  const hasUnit = !!v.unit
  const long = (v.unit || '').length > 4
  return (
    <div className="mg-corr">
      {[0, 1].map((row) => (
        <div className={'mg-units r' + row} key={row}>
          {[0, 1, 2, 3].map((i) => {
            const on = hasUnit && row === 0 && i === 1
            return <div key={i} className={'mg-unit' + (on ? ' on' : '')}>{on ? <span className={long ? 'sm' : ''}>{v.unit}</span> : null}</div>
          })}
        </div>
      ))}
      <span className="mg-aisle">راهرو</span>
      {hasUnit ? <>
        <svg className="mg-arrow" width="20" height="34" viewBox="0 0 20 34" fill="none" stroke="#e6395c" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M10 32V3M2 11l8-8 8 8" /></svg>
        <span className="mg-path" />
      </> : null}
      <Mascot pose="search" size={hasUnit ? 84 : 96} className={'mg-corr-m bob' + (hasUnit ? '' : ' mid')} />
    </div>
  )
}

function Building() {
  return (
    <div className="mg-bld">
      <div className="mg-tower">
        <div className="mg-win">{Array.from({ length: 12 }).map((_, i) => <i key={i} />)}</div>
        <div className="mg-door"><i /></div>
      </div>
      <div className="mg-ground" />
      <span className="mg-cap">ورودی پاساژ</span>
      <Mascot pose="wave" size={124} className="mg-bld-m bob" />
    </div>
  )
}

function ShopSign({ v }: { v: Extract<Step['visual'], { type: 'shop' }> }) {
  return (
    <div className="mg-shopv">
      <div className="mg-sign">
        <div className="mg-awn">{Array.from({ length: 9 }).map((_, i) => <i key={i} />)}</div>
        <b>{v.name}</b>
        {v.unit_label ? <small>{v.unit_label}</small> : null}
      </div>
      <Mascot pose="found" size={170} className="mg-shop-m pop" />
    </div>
  )
}

/** «مجتمع پارکینگ دارد.» -> «پارکینگ دارد» (cited text kept, only the subject/period trimmed) */
const factText = (t: string) => t.replace(/^(این\s+)?(مجتمع|پاساژ|مرکز\s*خرید)(\s+تجاری)?\s+/, '').replace(/[.。]\s*$/, '')
function SrcLink({ s }: { s: { url: string; host?: string; title: string } }) {
  return <a className="mg-src" href={s.url} target="_blank" rel="noreferrer" title={s.title}>منبع: <bdi dir="ltr">{s.host || s.title}</bdi></a>
}

/* ------------------------------------------------------------------ story */
export function MallGuideStory({ guide, sbar = false, onClose, onAsk, onContact, autoplay = false, startAt = 0 }: {
  guide: Guide; sbar?: boolean; onClose: () => void; onAsk?: () => void; onContact?: () => void; autoplay?: boolean; startAt?: number
}) {
  const steps = guide.steps
  const N = steps.length
  const [idx, setIdx] = useState(Math.min(startAt, N - 1))
  const [dir, setDir] = useState<1 | -1>(1)
  const [paused, setPaused] = useState(false)
  const [prog, setProg] = useState(0)
  const [mode, setMode] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const [drag, setDrag] = useState(0)
  const host = useMemo(() => (document.querySelector('.screen') as HTMLElement | null) || document.body, [])
  const st = steps[idx]

  const close = useCallback(() => { setLeaving(true); window.setTimeout(onClose, 220) }, [onClose])
  const go = useCallback((d: 1 | -1) => {
    setIdx((i) => { const n = Math.max(0, Math.min(N - 1, i + d)); if (n !== i) { setDir(d); setProg(0); setMode(0) } return n })
  }, [N])

  // optional auto-advance (spec: off by default; 6 s; the last step stays)
  useEffect(() => {
    if (!autoplay || paused || idx >= N - 1) return
    let raf = 0; const t0 = performance.now() - prog * AUTO_MS
    const tick = (t: number) => { const p = (t - t0) / AUTO_MS; if (p >= 1) { go(1); return } setProg(p); raf = requestAnimationFrame(tick) }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, paused, idx, N, go])

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowLeft') go(1)          // RTL: left = forward
      else if (e.key === 'ArrowRight') go(-1)
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [close, go])

  // gestures: tap left 2/3 = next, right 1/3 = previous; long-press = pause; swipe down = close
  const g = useRef<{ x: number; y: number; t: number; held: boolean; timer: number; id: number } | null>(null)
  const down = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button,a,[data-notap]')) return
    const timer = window.setTimeout(() => { if (g.current) { g.current.held = true; setPaused(true) } }, 230)
    g.current = { x: e.clientX, y: e.clientY, t: Date.now(), held: false, timer, id: e.pointerId }
  }
  const move = (e: React.PointerEvent) => {
    const s = g.current; if (!s) return
    const dy = e.clientY - s.y, dx = e.clientX - s.x
    if (Math.abs(dx) > 12 || Math.abs(dy) > 12) window.clearTimeout(s.timer)
    if (dy > 0 && dy > Math.abs(dx)) setDrag(dy)
  }
  const up = (e: React.PointerEvent) => {
    const s = g.current; g.current = null; if (!s) return
    window.clearTimeout(s.timer)
    const dy = e.clientY - s.y, dx = e.clientX - s.x
    setDrag(0)
    if (s.held) { setPaused(false); return }
    if (dy > 90 && Math.abs(dx) < 90) { close(); return }
    if (Math.abs(dx) > 14 || Math.abs(dy) > 14) return
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    if (e.clientX - r.left < r.width * (2 / 3)) go(1); else go(-1)
  }
  const cancel = () => { const s = g.current; g.current = null; if (s) { window.clearTimeout(s.timer); if (s.held) setPaused(false) } setDrag(0) }

  const modes = st.modes || []
  const sub = st.kind === 'floor' && modes.length ? modes[Math.min(mode, modes.length - 1)].text : st.text
  const src = st.kind === 'floor' && modes.length ? modes[Math.min(mode, modes.length - 1)].source || null : st.source || null
  const v = st.visual
  const facts = (st.facts || []).filter((f) => f.source)
  const shopV = v.type === 'shop' ? v : null

  const node = (
    <div className={'mg-story' + (leaving ? ' out' : '') + (paused ? ' paused' : '')} role="dialog" aria-modal="true" aria-label={`راهنمای رسیدن به ${guide.shop_name}`} dir="rtl"
      style={drag ? { transform: `translateY(${Math.min(drag, 400) * 0.6}px)`, opacity: 1 - Math.min(drag, 400) / 900 } : undefined}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel} onContextMenu={(e) => e.preventDefault()}>
      {sbar ? <StatusBar /> : <div className="mg-safe" />}
      <div className="mg-chrome">
        <div className="mg-prog" aria-hidden>
          {steps.map((_, i) => (
            <span key={i} className="mg-seg"><i key={i === idx ? 'c' + idx : 's'} className={i < idx ? 'done' : i === idx ? (autoplay && idx < N - 1 ? 'cur auto' : 'cur') : ''}
              style={i === idx && autoplay && idx < N - 1 ? { transform: `scaleX(${prog})` } : undefined} /></span>
          ))}
        </div>
        <div className="mg-head">
          <span className="mg-av"><img src={avatar} alt="" /></span>
          <span className="mg-ht"><b>{guide.mall}</b><small>راهنمای رسیدن به {guide.shop_name}</small></span>
          <button className="mg-x" onClick={close} aria-label="بستن"><Close /></button>
        </div>
      </div>

      <div className={'mg-frame ' + (dir > 0 ? 'fwd' : 'back')} key={idx}>
        <div className={'mg-art' + (st.kind === 'shop' ? ' short' : '') + (st.photo ? ' photo' : '')}>
          {st.photo ? <>
            <img className="mg-photo" src={st.photo.url} alt={guide.mall || ''} />
            <a className="mg-credit" href={st.photo.source_url} target="_blank" rel="noreferrer">منبع: {st.photo.source_title}</a>
          </> : v.type === 'building' ? <Building /> : v.type === 'floors' ? <>
            {modes.length > 1 ? (
              <div className="mg-toggle" data-notap>
                {modes.map((m, i) => <button key={m.key} className={i === mode ? 'on' : ''} onClick={() => setMode(i)}>{m.label}</button>)}
              </div>) : null}
            <Floors v={v} />
          </> : v.type === 'corridor' ? <Corridor v={v} /> : shopV ? <ShopSign v={shopV} /> : null}
        </div>

        <div className="mg-text">
          <span className="mg-step">مرحلهٔ {fa(idx + 1)} از {fa(N)}</span>
          <h1 className={st.title.length > 24 ? 'long' : ''}>{st.title}</h1>
          {sub ? <p>{sub}</p> : null}
          {st.text2 ? <p>{st.text2}</p> : null}
          {shopV && (shopV.open_label || shopV.price_label) ? (
            <p className="mg-meta">
              {shopV.open_label ? <span><i className={'mg-dot' + (shopV.open ? ' on' : '')} />{shopV.open_label}</span> : null}
              {shopV.open_label && shopV.price_label ? <span className="mg-sep">·</span> : null}
              {shopV.price_label ? <span className="mg-price">{shopV.price_label}</span> : null}
            </p>) : null}
          {facts.length ? <p className="mg-facts"><bdi>{facts.map((f) => factText(f.text)).join(' · ')}</bdi><SrcLink s={facts[0].source!} /></p> : null}
          {src ? <p className="mg-facts"><SrcLink s={src} /></p> : null}
        </div>

        {st.kind === 'arrive' && st.links ? (
          <div className="mg-btns">
            <a className="mg-btn mg-sec" href={st.links.neshan} target="_blank" rel="noreferrer"><Nav /> مسیریابی با نشان</a>
            <a className="mg-btn mg-sec" href={st.links.google} target="_blank" rel="noreferrer">گوگل‌مپ</a>
          </div>
        ) : st.kind === 'shop' && (onAsk || onContact) ? (
          <div className="mg-btns col">
            {onAsk ? <button className="mg-btn mg-pri" onClick={() => { onAsk(); close() }}><img src={avatar} alt="" /> دربارهٔ این مغازه بپرس</button> : null}
            {onContact ? <button className="mg-btn mg-sec" onClick={() => { close(); window.setTimeout(onContact, 230) }}>تماس</button> : null}
          </div>
        ) : null}
      </div>
    </div>
  )
  return createPortal(node, host)
}

/* ------------------------------------------------------------------ wrapper: entry row + story (+ lazy cited facts) */
export function MallGuide({ sid, pid, sbar, onAsk, onContact, autoplay }: {
  sid: string; pid?: string | null; sbar?: boolean; onAsk?: () => void; onContact?: () => void; autoplay?: boolean
}) {
  const [guide, setGuide] = useState<Guide | null>(null)
  const [open, setOpen] = useState(false)
  const asked = useRef(false)
  useEffect(() => {
    let alive = true
    setGuide(null); asked.current = false
    getGuide(sid, pid).then((g) => alive && setGuide(g)).catch(() => alive && setGuide(null))
    return () => { alive = false }
  }, [sid, pid])
  const openStory = () => {
    setOpen(true)
    if (guide && guide.facts_status === 'not_fetched' && !asked.current) {      // first open of this mall: one cited lookup, then merge
      asked.current = true
      getGuideWithFacts(sid, pid).then((g) => { if (g?.eligible && g.steps.length === guide.steps.length) setGuide(g) }).catch(() => undefined)
    }
  }
  if (!guide || !guide.eligible) return null
  return <>
    <MallGuideEntry guide={guide} onOpen={openStory} />
    {open ? <MallGuideStory guide={guide} sbar={sbar} autoplay={autoplay} onClose={() => setOpen(false)} onAsk={onAsk} onContact={onContact} /> : null}
  </>
}
export default MallGuide
