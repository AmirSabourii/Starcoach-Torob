import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError, errText, sendStream, SID } from './api'
import { Home } from './Home'
import { ChatScreen, QuestionSheet, type Msg, type Question, type R } from './Chat'
import { CategoryScreen, DealsScreen, AreaSheet, type Area } from './Lists'
import { ProductPage } from './Product'
import { ShopSheet } from './Shop'
import { ProjectResults, type ProjectR, type SearchR } from './Project'
import { MapTab } from './MapView'
import { StatusBar } from './StatusBar'
import { Toast, useAssistantState, type Attachment, type GridProduct } from './ui'
import { BackIcon } from './icons'

type Screen = { k: 'home' } | { k: 'chat' } | { k: 'cat'; key: string; label: string } | { k: 'deals' } | { k: 'project'; r: SearchR; sent: number; p: ProjectR } | { k: 'chatmap'; q: string }
type Overlay = { k: 'product'; id: string; tab?: 'summary' | 'sellers' } | { k: 'shop'; id: string; pid?: string | null; alt?: boolean } | { k: 'area' }

const FALLBACK_AREA: Area = { key: 'ونک', label: 'ونک', lat: 35.757, lon: 51.41 }
let MID = 1

export default function App() {
  const sbar = useMemo(() => new URLSearchParams(location.search).has('statusbar') || window.matchMedia('(min-width: 560px) and (min-height: 700px)').matches, [])
  const [stack, setStack] = useState<Screen[]>([{ k: 'home' }])
  const [overlays, setOverlays] = useState<Overlay[]>([])
  const [tab, setTab] = useState<'chat' | 'map'>('chat')
  const [areas, setAreas] = useState<Area[]>([FALLBACK_AREA])
  const [area, setArea] = useState<Area>(() => { try { return JSON.parse(localStorage.getItem('torob_app_area') || '') as Area } catch { return FALLBACK_AREA } })
  const [deals, setDeals] = useState<GridProduct[] | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [busy, setBusy] = useState(false)
  const convStarted = useRef(false)   // first message after page load = a new conversation (server starts a clean session)
  const [doneTick, setDoneTick] = useState(0)
  const [qs, setQs] = useState<Question[] | null>(null)
  const [toastText, setToastText] = useState<string | null>(null)
  const [initAtt, setInitAtt] = useState<Attachment | null>(null)
  const toastT = useRef(0)
  const mascot = useAssistantState(busy, doneTick)

  const toast = useCallback((t: string) => { setToastText(t); window.clearTimeout(toastT.current); toastT.current = window.setTimeout(() => setToastText(null), 2200) }, [])
  useEffect(() => {
    api<{ areas: Area[] }>('/api/home/areas').then((r) => setAreas(r.areas)).catch(() => {})
    api<{ items: GridProduct[] }>('/api/home/deals?limit=6').then((r) => setDeals(r.items)).catch(() => setDeals([]))
  }, [])
  useEffect(() => { localStorage.setItem('torob_app_area', JSON.stringify(area)) }, [area])

  const push = (s: Screen) => setStack((x) => [...x, s])
  const pop = () => setStack((x) => (x.length > 1 ? x.slice(0, -1) : x))
  const openProduct = useCallback((id: string, tab?: 'summary' | 'sellers') => setOverlays((o) => [...o, { k: 'product', id, tab }]), [])
  const openShop = useCallback((id: string, pid?: string | null, alt?: boolean) => setOverlays((o) => [...o, { k: 'shop', id, pid, alt }]), [])
  useEffect(() => {   // deep link: /app?shop=<shop_id>&pid=<product_id> opens that shop sheet
    const u = new URLSearchParams(location.search), sh = u.get('shop')
    if (sh && /^shop_[0-9a-f]+$/.test(sh)) openShop(sh, u.get('pid'))
  }, [openShop])
  useEffect(() => {   // deep link: /app?product=<product_id> opens that product page
    const pr = new URLSearchParams(location.search).get('product')
    if (pr && /^product_[0-9a-f]+$/.test(pr)) openProduct(pr)
  }, [openProduct])
  const closeTop = () => setOverlays((o) => o.slice(0, -1))
  const top = stack[stack.length - 1]

  const send = useCallback(async (text: string, att?: Attachment | null, answers?: { id: string; title: string; answer: string }[], extra?: Record<string, unknown>) => {
    if (!text.trim() || busy) return
    const id = MID++
    setMsgs((m) => [...m, { id: MID++, role: 'user', text, att: att || null }, { id, role: 'bot', pending: true }])
    setBusy(true)
    const msg = extra && extra.project ? `دربارهٔ همین فهرست «خرید یکجا» که الان جلومه (از قبل آماده شده، دوباره سؤال نپرس): ${text}` : text
    const qp = new URLSearchParams(location.search)       // demo/test override of the current Tehran time: /app/?now=23:30[&day=fri]
    const body = { message: msg, sid: SID, mode: 'v3plus', area: area.key, answers, ...(qp.get('now') ? { now: qp.get('now') } : {}), ...(qp.get('day') ? { day: qp.get('day') } : {}), ...(extra || {}), ...(convStarted.current ? {} : { new_conversation: true }) }
    convStarted.current = true
    const patch = (f: (x: any) => any) => setMsgs((m) => m.map((x) => (x.id === id ? f(x) : x)))
    try {
      let j: { results: R[] }
      try {
        let txt = ''
        j = await sendStream(body, ({ event, data }) => {
          if (event === 'status') patch((x) => ({ ...x, stage: data.stage, nFound: data.n_found ?? x.nFound }))
          // cards: ONE event per turn with the final, server-checked selection (raw search results are never streamed)
          else if (event === 'cards') patch((x) => { if (x.cards) { console.error('[stream] second cards event ignored'); return x } return { ...x, cards: data.items || [] } })
          else if (event === 'text') { txt += data.chunk || ''; patch((x) => ({ ...x, stage: 'writing', partial: txt })) }
        })
      } catch (e) {
        if (!(e instanceof ApiError) || e.kind !== 'nostream') throw e
        j = await api<{ results: R[] }>('/api/send', { body, timeout: 120000 })     // stream unavailable -> plain send (nothing was sent yet)
      }
      let r = j.results[0]
      setMsgs((m) => m.map((x: any) => {
        if (x.id !== id) return x
        if (r.ok === false) return { id, role: 'bot', error: 'نشد جواب بدم؛ یه بار دیگه بپرس.', retry: text }
        const shown: any[] | undefined = x.cards
        if (shown && shown.length) {       // cards already on screen: never replace or reorder them
          const fin = (r.blocks || []).filter((b: any) => b.type === 'product_cards').flatMap((b: any) => b.items.map((p: any) => p.product_id)).join(',')
          if (fin !== shown.map((p) => p.product_id).join(',')) {
            console.error('[stream] final cards differ from streamed cards (should be impossible); keeping the streamed ones', fin)
            const rest = (r.blocks || []).filter((b: any) => b.type !== 'product_cards')
            r = { ...r, blocks: [{ type: 'product_cards', items: shown }, ...rest] }
          }
        }
        return { id, role: 'bot', r }
      }))
      if (r.questions?.length) setQs(r.questions)
      setDoneTick((t) => t + 1)
    } catch (e) {
      setMsgs((m) => m.map((x) => (x.id === id ? { id, role: 'bot', error: errText(e), retry: text } : x)))
    } finally { setBusy(false) }
  }, [busy, area.key])

  const ask = (q: string, att?: Attachment | null) => {
    if (top.k !== 'chat') push({ k: 'chat' })
    if (q) send(q, att)
    else setInitAtt(att || null)
  }
  const clearChip = async (key: string) => {
    try {
      const r = await api<{ chips: { key: string; label: string }[] }>('/api/memory/clear', { body: { sid: SID, version: 'v3plus', key } })
      setMsgs((m) => { const i = [...m].reverse().findIndex((x) => x.role === 'bot' && 'r' in x && x.r); if (i < 0) return m; const k = m.length - 1 - i; const x = m[k] as any; return m.map((y, j) => (j === k ? { ...x, r: { ...x.r, memory: { chips: r.chips } } } : y)) })
    } catch (e) { toast(errText(e)) }
  }
  const lastUserQ = [...msgs].reverse().find((m) => m.role === 'user') as Extract<Msg, { role: 'user' }> | undefined

  return (
    <div className="device">
      <main className="screen">
        {stack.map((s, i) => {
          const hidden = i !== stack.length - 1
          const wrap = (el: JSX.Element) => <div key={i + s.k} className="layer" style={{ display: hidden ? 'none' : undefined }}>{el}</div>
          if (s.k === 'home') return wrap(<Home tab={tab} setTab={setTab} onAsk={ask} onTile={(key, label) => push({ k: 'cat', key, label })} onDeals={() => push({ k: 'deals' })}
            onOpen={openProduct} onShop={openShop} area={area.key} areaLabel={area.label} onArea={() => setOverlays((o) => [...o, { k: 'area' }])} deals={deals} sbar={sbar} />)
          if (s.k === 'chat') return wrap(<><div className="sb-space">{sbar ? <StatusBar /> : null}</div><ChatScreen msgs={msgs} busy={busy} mascot={mascot} onSend={send} onBack={pop} onOpen={openProduct} onShop={openShop}
            onTab={() => push({ k: 'chatmap', q: lastUserQ?.text || '' })} area={area.key} areaLabel={area.label} onArea={() => setOverlays((o) => [...o, { k: 'area' }])}
            onProject={(r, sent, p) => push({ k: 'project', r, sent, p })} onQuestions={setQs} toast={toast} onClearChip={clearChip} initAtt={initAtt} /></>)
          if (s.k === 'cat') return wrap(<><div className="sb-space">{sbar ? <StatusBar /> : null}</div><CategoryScreen tkey={s.key} label={s.label} onBack={pop} onOpen={openProduct} /></>)
          if (s.k === 'deals') return wrap(<><div className="sb-space">{sbar ? <StatusBar /> : null}</div><DealsScreen onBack={pop} onOpen={openProduct} /></>)
          if (s.k === 'project') return wrap(<><div className="sb-space">{sbar ? <StatusBar /> : null}</div><ProjectResults r={s.r} sent={s.sent} p={s.p} onBack={pop} onShop={openShop} onProduct={openProduct} toast={toast} areaLabel={area.label} start={[area.lat, area.lon]} busy={busy}
            onFollow={(t, ctx) => { pop(); send(t, null, undefined, ctx ? { project: ctx } : undefined) }} /></>)
          if (s.k === 'chatmap') return wrap(<><div className="sb-space">{sbar ? <StatusBar /> : null}</div><div className="screen-page"><div className="page-h"><button className="icon-btn" onClick={pop} aria-label="بازگشت"><BackIcon /></button><h1>نقشهٔ فروشگاه‌ها</h1><span style={{ width: 36 }} /></div>
            <MapTab area={area.key} areaLabel={area.label} onShop={openShop} onArea={() => setOverlays((o) => [...o, { k: 'area' }])} query={s.q} /></div></>)
          return null
        })}
        {overlays.map((o, i) => {
          if (o.k === 'product') return <ProductPage key={i + o.id} pid={o.id} tab0={o.tab} area={area.key} areaLabel={area.label} sbar={sbar} onClose={closeTop} onShop={openShop} toast={toast} />
          if (o.k === 'shop') return <ShopSheet key={i + o.id} sid={o.id} pid={o.pid} alt={o.alt} sbar={sbar} onClose={closeTop} onProduct={(p) => openProduct(p)} toast={toast} onShop={(sid2, pid2) => openShop(sid2, pid2)} />
          return <AreaSheet key={i + 'area'} areas={areas} cur={area.key} onClose={closeTop} onPick={(a) => { setArea(a); closeTop(); toast('محدوده: ' + a.label) }} />
        })}
        {qs && top.k === 'chat' ? <QuestionSheet qs={qs} onClose={() => setQs(null)} onSend={(ans, text) => { setQs(null); send(text, null, ans) }} /> : null}
        <Toast text={toastText} />
        {sbar ? <div className="homebar" aria-hidden /> : null}
      </main>
    </div>
  )
}
