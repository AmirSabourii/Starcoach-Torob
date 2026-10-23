// In-store shopping (spec-instore.md): «پیش از خرید» (fair price + «چی بپرسم؟» + authenticity), seller-quoted price notes,
// «اینجا نداشت» alternatives, other shops in the same mall + cited mall facts. All DB/static, $0.
import { useEffect, useState, type ReactNode } from 'react'
import { api, SID } from '../api'
import { fa, faNum, short } from '../fmt'
import { Img, Sheet } from '../ui'
import './instore.css'

type Fair = { ok: boolean; n_sellers: number; lo?: number; hi?: number; p25?: number; p75?: number; label?: string; gouge_label?: string; lo_label?: string; hi_label?: string }
type BB = { fair: Fair | null; questions: string[]; auth: string[]; auth_note: string }
type Note = { sid: string; name: string; price: number }
const bbCache: Record<string, Promise<BB>> = {}
const getBB = (pid: string) => (bbCache[pid] ||= api<BB>(`/api/product/${pid}/before_buy`))
const today = () => new Date().toISOString().slice(0, 10)
const nkey = (pid: string) => `instore_notes_${pid}_${today()}`
export const readNotes = (pid: string): Note[] => { try { return JSON.parse(localStorage.getItem(nkey(pid)) || '[]') } catch { return [] } }
const writeNote = (pid: string, n: Note) => {
  const all = readNotes(pid).filter((x) => x.sid !== n.sid); all.push(n)
  localStorage.setItem(nkey(pid), JSON.stringify(all)); window.dispatchEvent(new Event('instore-notes'))
}
const mil = (v: number) => (v >= 1e6 ? fa((Math.round(v / 1e5) / 10).toString()).replace('.', '٫') + ' میلیون' : faNum(Math.round(v / 1000)) + ' هزار')
function useNotes(pid: string) {
  const [n, setN] = useState<Note[]>(() => readNotes(pid))
  useEffect(() => { const f = () => setN(readNotes(pid)); window.addEventListener('instore-notes', f); return () => window.removeEventListener('instore-notes', f) }, [pid])
  return n
}
function useBB(pid?: string | null) {
  const [bb, setBB] = useState<BB | null>(null)
  useEffect(() => { let a = true; if (pid) getBB(pid).then((r) => { if (a) setBB(r) }).catch(() => {}); return () => { a = false } }, [pid])
  return bb
}

function FairBar({ f, notes }: { f: Fair; notes: Note[] }) {
  if (!f.ok || f.lo == null || f.hi == null) return null
  const span = Math.max(1, f.hi - f.lo)
  const pos = (v: number) => Math.min(100, Math.max(0, ((v - f.lo!) / span) * 100))
  return (
    <div className="is-fair">
      <b>{f.label}</b>
      <span className="is-sub">{f.gouge_label}</span>
      <div className="is-bar">
        <i className="is-band" style={{ right: pos(f.p25!) + '%', width: Math.max(2, pos(f.p75!) - pos(f.p25!)) + '%' }} />
        {notes.map((n) => <i key={n.sid} className="is-mark" style={{ right: `calc(${pos(n.price)}% - 5px)` }} />)}
      </div>
      <div className="is-ends"><span>{f.lo_label}</span><span>{f.hi_label}</span></div>
    </div>
  )
}
function NotesList({ notes }: { notes: Note[] }) {
  if (!notes.length) return null
  return <div className="is-notes">{notes.map((n) => <div key={n.sid}>{n.name}: {mil(n.price)}، گفتهٔ فروشنده</div>)}</div>
}

type Advice = { questions: string[]; tips: string[]; source: string }
const advCache: Record<string, Promise<Advice>> = {}
function useAdvice(pid: string, on: boolean, shopId?: string | null, notes: Note[] = []) {
  const [a, setA] = useState<Advice | null>(null)
  const key = pid + '|' + (shopId || '') + '|' + notes.map((n) => n.sid + n.price).join(',')
  useEffect(() => {
    if (!on) return
    let alive = true; setA(null)
    ;(advCache[key] ||= api<Advice>(`/api/product/${pid}/advice`, { body: { shop_id: shopId || null, notes: notes.map((n) => ({ name: n.name, price: n.price })), sid: SID }, timeout: 25000 }))
      .then((r) => { if (alive) setA(r) }).catch(() => { delete advCache[key]; if (alive) setA({ questions: [], tips: [], source: 'error' }) })
    return () => { alive = false }
  }, [on, key]) // eslint-disable-line react-hooks/exhaustive-deps
  return a
}

/** «پیش از خرید» (product page summary tab, chat chip): fair band (DB) + questions/tips written for this shopper by the model (lazy, cached) */
export function BeforeBuy({ pid, defaultOpen = false, only, shopId }: { pid: string; defaultOpen?: boolean; only?: 'fair' | 'questions'; shopId?: string | null }) {
  const bb = useBB(pid); const notes = useNotes(pid)
  const [open, setOpen] = useState(defaultOpen)
  const adv = useAdvice(pid, open && only !== 'fair', shopId, notes)
  if (!bb) return null
  const hasFair = !!bb.fair?.ok
  return (
    <section className={'is-card' + (open ? ' open' : '')}>
      <button className="is-row" onClick={() => setOpen((x) => !x)} aria-expanded={open}><span>پیش از خرید</span><i className="is-chev" /></button>
      {open ? (
        <div className="is-body">
          {only === 'questions' ? null : <div className="is-sec">{hasFair ? <FairBar f={bb.fair!} notes={notes} /> : <span className="is-sub">برای این محصول قیمت کافی نداریم</span>}</div>}
          {notes.length && only !== 'questions' ? <div className="is-sec"><b className="is-h">مقایسهٔ یادداشت‌های امروز</b><NotesList notes={notes} /></div> : null}
          {only === 'fair' ? null : !adv ? (
            <div className="is-sec is-skel" aria-hidden><b className="is-h">چی بپرسم؟</b><i /><i /><i /></div>
          ) : adv.questions.length ? (
            <>
              <div className="is-sec"><b className="is-h">چی بپرسم؟</b><ul className="is-q">{adv.questions.map((q) => <li key={q}>{q}</li>)}</ul></div>
              {adv.tips.length ? <div className="is-sec"><b className="is-h">حواست باشه</b><ul className="is-q">{adv.tips.map((q) => <li key={q}>{q}</li>)}</ul></div> : null}
            </>
          ) : null}
        </div>) : null}
    </section>
  )
}

/** sellers tab: only the fair-price bar (hidden when < 3 sellers) */
export function SellersFair({ pid }: { pid: string }) {
  const bb = useBB(pid); const notes = useNotes(pid)
  if (!bb?.fair?.ok) return null
  return <div className="is-card pad"><FairBar f={bb.fair} notes={notes} /><NotesList notes={notes} /></div>
}

type Stop = { shop_id: string; name: string; where: string; price_label: string; is_current: boolean }
type Mates = { in_mall: boolean; mall?: string; stops: Stop[]; n_other: number; label?: string | null; facts?: { rows: { kind: string; label: string; text: string; source_url: string; host: string }[] } | null }
type Alt = { product_id: string; title: string; image: string | null; shop_id: string; shop_name: string; price_label: string; where: string }

/** shop sheet: price note, «اینجا نداشت», other shops in this mall, cited mall facts */
export function ShopInStore({ sid, pid, has, shopName, toast, onShop, onProduct, onMap, showAlts, fallback, preferFallback }: {
  sid: string; pid?: string | null; has?: boolean; shopName: string; toast: (t: string) => void; showAlts?: boolean; fallback?: ReactNode; preferFallback?: boolean
  onShop?: (sid: string, pid: string) => void; onProduct: (pid: string) => void; onMap?: () => void
}) {
  const [mates, setMates] = useState<Mates | null>(null)
  const [noteOpen, setNoteOpen] = useState(false)
  const [amt, setAmt] = useState('')
  const [alts, setAlts] = useState<{ same_shop: Alt[]; neighbours: Alt[] } | null | 'loading'>(null)
  const [stopsOpen, setStopsOpen] = useState(false)
  const [factsOpen, setFactsOpen] = useState(false)
  useEffect(() => { let a = true; api<Mates>(`/api/shop/${sid}/mallmates${pid ? '?pid=' + pid : ''}`).then((r) => { if (a) setMates(r) }).catch(() => {}); return () => { a = false } }, [sid, pid])
  useEffect(() => {    // «جایگزین» in the action row: same shop -> neighbour shop in the mall -> nearby
    if (!showAlts || !pid) { setAlts(null); return }
    let a = true
    setAlts('loading'); api<any>(`/api/shop/${sid}/alts_here?pid=${pid}`).then((r) => { if (a) setAlts(r) }).catch(() => { if (a) setAlts({ same_shop: [], neighbours: [] }) })
    return () => { a = false }
  }, [showAlts, sid, pid])
  const press = (k: string) => setAmt((x) => (k === '⌫' ? x.slice(0, -1) : (x + k).replace(/^0+/, '').slice(0, 11)))
  const val = parseInt(amt || '0', 10)
  const facts = mates?.facts?.rows || []
  return (
    <div className="is-shop">
      {pid && has ? <button className="is-note-btn" onClick={() => { setAmt(''); setNoteOpen(true) }}>قیمتی که گفت رو بنویس</button> : null}
      {showAlts && preferFallback ? fallback : null}
      {alts === 'loading' ? <div className="is-sub pad">…</div> : alts ? (
        alts.same_shop.length + alts.neighbours.length ? (
          <div className="is-alts">
            {alts.same_shop.length ? <div className="is-slider">{alts.same_shop.map((a) => <AltTile key={a.product_id} a={a} onProduct={onProduct} />)}</div> : null}
            {alts.neighbours.length ? <>
              <b className="is-h">{alts.neighbours[0].where}</b>
              <div className="is-slider">{alts.neighbours.map((a) => <AltTile key={a.product_id + a.shop_id} a={a} onProduct={onProduct} onShop={onShop ? () => onShop(a.shop_id, a.product_id) : undefined} />)}</div>
            </> : null}
          </div>
        ) : preferFallback ? null : (fallback || <div className="is-empty"><span>مشابهی این نزدیکی پیدا نکردم</span>{onMap ? <button className="is-text-btn" onClick={onMap}>روی نقشه ببین</button> : null}</div>)
      ) : null}
      {mates?.label && pid ? (
        <section className={'is-card' + (stopsOpen ? ' open' : '')}>
          <button className="is-row" onClick={() => setStopsOpen((x) => !x)} aria-expanded={stopsOpen}><span>{mates.label}</span><i className="is-chev" /></button>
          {stopsOpen ? <div className="is-stops">{mates.stops.map((s, i) => (
            <button key={s.shop_id} className={'is-stop' + (s.is_current ? ' cur' : '')} disabled={s.is_current} onClick={() => onShop && pid && onShop(s.shop_id, pid)}>
              <span className="is-n">{fa(i + 1)}</span>
              <span className="is-st"><b>{s.name}</b><small>{s.where}</small></span>
              <span className="is-p">{s.price_label}</span>
            </button>))}</div> : null}
        </section>) : null}
      {facts.length ? (
        <section className={'is-card' + (factsOpen ? ' open' : '')}>
          <button className="is-row" onClick={() => setFactsOpen((x) => !x)} aria-expanded={factsOpen}><span>رسیدن به پاساژ</span><i className="is-chev" /></button>
          {factsOpen ? <div className="is-facts">{facts.filter((f, i, a) => a.findIndex((x) => x.kind === f.kind) === i).slice(0, 4).map((f, i) => <p key={i}><b>{f.label}</b> {f.text} <a href={f.source_url} target="_blank" rel="noreferrer">منبع: {f.host}</a></p>)}</div> : null}
        </section>) : null}
      {noteOpen && pid ? (
        <Sheet onClose={() => setNoteOpen(false)} className="is-pad">
          <div className="is-amt">{val ? faNum(val) : fa(0)} <small>تومان</small></div>
          <div className="is-keys">{['1', '2', '3', '4', '5', '6', '7', '8', '9', '000', '0', '⌫'].map((k) => <button key={k} onClick={() => press(k)}>{k === '⌫' ? k : fa(k)}</button>)}</div>
          <button className="btn-ink is-save" disabled={!val} onClick={() => { writeNote(pid, { sid, name: shopName, price: val }); setNoteOpen(false); toast('ثبت شد') }}>ثبت</button>
        </Sheet>) : null}
    </div>
  )
}
function AltTile({ a, onProduct, onShop }: { a: Alt; onProduct: (pid: string) => void; onShop?: () => void }) {
  return (
    <button className="is-tile" onClick={() => (onShop ? onShop() : onProduct(a.product_id))}>
      <span className="is-tim"><Img src={a.image} /></span>
      <span className="is-tt">{short(a.title, 38)}</span>
      <b>{a.price_label}</b>
      <small>{a.shop_name}</small>
    </button>
  )
}
