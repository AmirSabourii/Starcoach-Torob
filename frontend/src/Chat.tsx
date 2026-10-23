import { useEffect, useRef, useState } from 'react'
import { api, CID, errText } from './api'
import { clean, fa, faNum, short, splitTitle, stripParen, toman, UNKNOWN } from './fmt'
import { BackIcon, Heart, Pin, Store, UserIcon, ChevLeft, Close, PencilIcon } from './icons'
import { Composer, Img, MascotAvatar, type Attachment } from './ui'
import type { MascotState } from './useMascot'
import { BazaarCard, type Bazaar } from './Drawer'
import { AltBox, type AltR } from './Shop'
import { LateNight } from './LateNight'
import { PlanUpdateCard, ProjectChecklist, type ProjectR, type SearchR } from './Project'

export type Question = { id: string; title: string; type: 'single' | 'multi' | 'text' | 'range'; options: { label: string; value?: string }[]; allow_custom?: boolean }
export type R = {
  ok?: boolean; text: string; blocks: any[]; related?: any[]; suggestions?: string[]; questions?: Question[]; refine?: { id: string; title: string; options: string[] }[]; project_result?: SearchR; alternatives?: AltR
  memory?: { chips: { key: string; label: string }[] }; list_hook?: { label: string; product_id: string; shop_id: string | null; offer_id: string | null; title: string; shop_name: string | null } | null
  bazaar?: Bazaar | null; project?: ProjectR; metrics?: { cost_usd?: number; llm_calls?: number; latency_s?: number }
}
export type Msg = { id: number; role: 'user'; text: string; att?: Attachment | null } | { id: number; role: 'bot'; pending?: boolean; r?: R; error?: string; retry?: string; stage?: string; nFound?: number; cards?: any[]; partial?: string }

export type CardInfo = { product_id: string; title: string; image: string | null; min_price: number | null; max_price: number | null; n_shops: number; area_label: string }
function ProductCard({ p, info, onOpen, onSave, saved }: { p: any; info?: CardInfo; onOpen: (pid: string, tab?: 'summary' | 'sellers') => void; onSave: (pid: string) => void; saved: boolean }) {
  const [t1, t2] = splitTitle(p.title)
  const lo = info ? info.min_price : (p.min_price ?? null)
  const hi = info ? info.max_price : null
  const n = info ? info.n_shops : (p.shops ?? p.n_shops ?? 0)
  return (
    <div className="hpc" onClick={() => onOpen(p.product_id)} role="button">
      <div className="hpc-c">
        <div className="hpc-top">
          <div className="hpc-t"><b>{t1}</b>{t2 ? <span dir="ltr">{t2}</span> : null}</div>
          <button className="hpc-fav" aria-label="ذخیره" onClick={(e) => { e.stopPropagation(); onSave(p.product_id) }}><Heart on={saved} /></button>
        </div>
        <div className="hpc-p">{lo ? (hi && hi !== lo ? <><b>{faNum(lo)}</b> <i>تا</i> <b>{faNum(hi)}</b> <i>تومان</i></> : <><b>{faNum(lo)}</b> <i>تومان</i></>) : <b className="unk">{UNKNOWN}</b>}</div>
        <button className="hpc-row" onClick={(e) => { e.stopPropagation(); onOpen(p.product_id, 'sellers') }}><Pin size={15} color="#55566b" /><span>{info ? info.area_label : (p.areas?.join(' و ') || UNKNOWN)}</span><span className="chev-c"><ChevLeft size={9} /></span></button>
        <button className="hpc-row" onClick={(e) => { e.stopPropagation(); onOpen(p.product_id, 'sellers') }}><Store /><span>{fa(n)} فروشنده</span><span className="chev-c"><ChevLeft size={9} /></span></button>
      </div>
      <span className="hpc-im"><Img src={p.image} /></span>
    </div>
  )
}

function OfferCard({ o, onShop, onOpen }: { o: any; onShop: (s: string, p?: string) => void; onOpen: (p: string, tab?: 'summary' | 'sellers') => void }) {
  const sh = o.shop || {}
  const sid = o.shop_id || sh.shop_id
  return (
    <button className="ocard" onClick={() => (sid ? onShop(sid, o.product_id) : o.product_id && onOpen(o.product_id, 'sellers'))}>
      <span className="ocard-c"><b>{sh.name}</b>{sh.label ? <small><Pin size={11} color="#9a9aac" /> {sh.label}</small> : null}</span>
      {o.offer_id ? <span className="ocard-p">{o.price_toman ? <>{faNum(o.price_toman)}<small>تومان</small></> : <span className="unk">{UNKNOWN}</span>}{o.stale ? <span className="flag stale">قیمت قدیمی</span> : null}</span> : null}
      <span className="chev-c"><ChevLeft size={9} /></span>
    </button>
  )
}

function Blocks({ r, onOpen, onShop, onSave, saved, cards, showSellers }: { showSellers: boolean; r: R; onOpen: (p: string, tab?: 'summary' | 'sellers') => void; onShop: (s: string, p?: string) => void; onSave: (p: string) => void; saved: Record<string, boolean>; cards: Record<string, CardInfo> }) {
  return (
    <>
      {(r.blocks || []).map((b, i) => {
        if (b.type === 'late_night') return <div className="blk" key={i}><LateNight b={b} onShop={onShop} /></div>
        if (b.type === 'product_cards') return <div className="blk" key={i}>{b.items.map((p: any) => <ProductCard key={p.product_id} p={p} info={cards[p.product_id]} onOpen={onOpen} onSave={onSave} saved={!!saved[p.product_id]} />)}</div>
        if (b.type === 'sellers' || b.type === 'verify') {
          if (b.type === 'verify' || !showSellers) return null      // sellers only when the shopper asked for them; otherwise one small action
          return <div className="blk" key={i}><div className="blk-t">فروشنده‌ها</div>{b.items.slice(0, 5).map((o: any, j: number) => <OfferCard key={o.offer_id || j} o={o} onShop={onShop} onOpen={onOpen} />)}</div>
        }
        if (b.type === 'compare') return (
          <div className="blk" key={i}><div className="blk-t">مقایسه</div>
            <div className="cmp-wrap"><table className="cmp"><tbody>
              <tr><th />{b.products.map((p: any) => <th key={p.product_id}><button className="lnk" onClick={() => onOpen(p.product_id)}>{short(p.title, 36)}</button></th>)}</tr>
              <tr><td>کمترین قیمت</td>{b.products.map((p: any) => <td key={p.product_id}>{toman(p.min_price)}</td>)}</tr>
              <tr><td>میانه</td>{b.products.map((p: any) => <td key={p.product_id}>{toman(p.median_price)}</td>)}</tr>
              <tr><td>فروشنده</td>{b.products.map((p: any) => <td key={p.product_id}>{fa(p.shops ?? '')}</td>)}</tr>
            </tbody></table></div></div>
        )
        if (b.type === 'map' && !showSellers) return null      // shop list = sellers → only on request
        if (b.type === 'map') return (
          <div className="blk" key={i}><div className="blk-t">فروشگاه‌ها</div>
            {b.pins.map((p: any, j: number) => (
              <button className="ocard" key={p.shop_id || j} onClick={() => onShop(p.shop_id)}>
                <span className="av num">{fa(j + 1)}</span>
                <span className="ocard-c"><b>{p.name}</b>{p.label ? <small>{p.label}</small> : null}</span><span className="chev-c"><ChevLeft size={9} /></span>
              </button>
            ))}</div>
        )
        if (b.type === 'plan') return (
          <div className="blk" key={i}><div className="blk-t">برنامهٔ خرید</div>
            {b.steps.map((s: any, j: number) => (
              <button className="ocard" key={j} onClick={() => s.shop?.shop_id && onShop(s.shop.shop_id)}>
                <span className="av num">{fa(j + 1)}</span>
                <span className="ocard-c"><b>{s.shop?.name || ''}</b>{s.note ? <small>{s.note}</small> : null}</span>
              </button>
            ))}</div>
        )
        return null
      })}
    </>
  )
}

const T: Record<string, (x: string) => string> = { budget: (x) => 'بودجه‌ام ' + x, price: (x) => 'بودجه‌ام ' + x, recipient: (x) => 'برای ' + x, gender: (x) => 'برای ' + x, for: (x) => 'برای ' + x, use: (x) => 'بیشتر برای ' + x, usage: (x) => 'بیشتر برای ' + x, area: (x) => 'حوالی ' + x, location: (x) => 'حوالی ' + x, size: (x) => 'سایز ' + x, brand: (x) => 'برند ' + x }
export const phrase = (a: { id: string; answer: string }) => (T[a.id] || T[a.id.split('_')[0]] || ((x: string) => x))(a.answer)
export function QuestionSheet({ qs, onSend, onClose }: { qs: Question[]; onSend: (ans: { id: string; title: string; answer: string }[], text: string) => void; onClose: () => void }) {
  const [i, setI] = useState(0)
  const [sel, setSel] = useState<Record<string, string[]>>({})
  const [custom, setCustom] = useState<Record<string, string>>({})
  const [open, setOpen] = useState(false)
  const [closing, setClosing] = useState(false)
  useEffect(() => { const r = requestAnimationFrame(() => setOpen(true)); return () => cancelAnimationFrame(r) }, [])
  const q = qs[i]
  const finish = (s2: Record<string, string[]>, c2: Record<string, string>) => {
    const answers = qs.map((x) => {
      const v = [...(s2[x.id] || [])]
      if (c2[x.id]?.trim()) v.push(c2[x.id].trim())
      return { id: x.id, title: x.title, answer: v.join(' و ') }
    }).filter((a) => a.answer)
    if (!answers.length) return
    setClosing(true)
    window.setTimeout(() => onSend(answers, answers.map(phrase).join('، ')), 260)
  }
  const next = (s2: Record<string, string[]>, c2: Record<string, string>) => { if (i < qs.length - 1) window.setTimeout(() => setI(i + 1), 220); else window.setTimeout(() => finish(s2, c2), 220) }
  const close = () => { setClosing(true); window.setTimeout(onClose, 280) }
  const pick = (label: string) => {
    const cur = sel[q.id] || []
    const on = cur.includes(label)
    const nx = q.type === 'multi' ? (on ? cur.filter((x) => x !== label) : [...cur, label]) : [label]
    const s2 = { ...sel, [q.id]: nx }
    setSel(s2)
    if (q.type !== 'multi') next(s2, custom)
  }
  const opts = q.options || []
  return (
    <div className={'fsheet-wrap' + (open && !closing ? ' open' : '')}>
      <div className="sheet-scrim" onClick={close} />
      <div className="fsheet qs" role="dialog">
        <div className="fs-h">
          <div className="pager">
            <button aria-label="قبلی" disabled={i === 0} onClick={() => setI(i - 1)}><svg viewBox="0 0 10 16" width="9" height="14"><path d="M2 2l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
            <span>{fa(i + 1)} از {fa(qs.length)}</span>
            <button aria-label="بعدی" disabled={i >= qs.length - 1} onClick={() => setI(i + 1)}><svg viewBox="0 0 10 16" width="9" height="14"><path d="M8 2 2 8l6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
          </div>
          <button className="circ sm grey" onClick={close} aria-label="بستن"><Close /></button>
        </div>
        <h3 className="qs-t">{q.title}</h3>
        <div className="qlist">
          {opts.map((o, k) => {
            const on = (sel[q.id] || []).includes(o.label)
            return <button key={o.label} className={'qrow' + (on ? ' on' : '')} aria-pressed={on} onClick={() => pick(o.label)}><span className="qnum">{fa(k + 1)}</span><span className="qlab">{o.label}</span></button>
          })}
          <form className="qrow custom" onSubmit={(e) => { e.preventDefault(); if (custom[q.id]?.trim()) next(sel, custom) }}>
            <span className="qnum pen"><PencilIcon size={14} /></span>
            <input value={custom[q.id] || ''} placeholder="جواب خودت رو بنویس..." enterKeyHint="send" onChange={(e) => setCustom((c) => ({ ...c, [q.id]: e.target.value }))} />
          </form>
        </div>
        {q.type === 'multi' || custom[q.id]?.trim() ? <button className="btn-ink wide qs-go" disabled={!(sel[q.id]?.length || custom[q.id]?.trim())} onClick={() => next(sel, custom)}>{i < qs.length - 1 ? 'بعدی' : 'ارسال'}</button> : null}
      </div>
    </div>
  )
}

const STAGE: Record<string, string> = { received: 'دارم فکر می‌کنم', thinking: 'دارم فکر می‌کنم', searching: 'دارم بین فروشگاه‌ها می‌گردم', writing: 'دارم جواب رو می‌نویسم', checking: 'دارم قیمت‌ها رو چک می‌کنم' }

function PinFill() {
  return <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M12 22s-7-6.4-7-12a7 7 0 0 1 14 0c0 5.6-7 12-7 12Z" fill="#ec5a5f" /><circle cx="12" cy="10" r="2.6" fill="#fff" /></svg>
}
/** next-prompt thumbnail: a pin for place prompts, otherwise a real product image from the last answer */
function Thumb({ text, imgs }: { text: string; imgs: string[] }) {
  if (/نزدیک|کجا|آدرس|نقشه|محله|حوالی/.test(text)) return <span className="nthumb pin"><PinFill /></span>
  const img = /مقایسه/.test(text) ? imgs[1] || imgs[0] : imgs[0]
  return <span className="nthumb"><Img src={img || null} /></span>
}

export function ChatScreen({ msgs, busy, mascot, onSend, onBack, onOpen, onShop, onTab, area, areaLabel, onArea, onProject, onQuestions, toast, onClearChip, initAtt }: {
  msgs: Msg[]; busy: boolean; mascot: MascotState; onSend: (t: string, att?: Attachment | null, answers?: any[]) => void; onBack: () => void
  onOpen: (p: string, tab?: 'summary' | 'sellers') => void; onShop: (s: string, p?: string) => void; onTab: () => void; area: string; areaLabel: string; onArea: () => void
  onProject: (r: SearchR, sent: number, p: ProjectR) => void; onQuestions: (qs: Question[]) => void; toast: (t: string) => void; onClearChip: (key: string) => void; initAtt?: Attachment | null
}) {
  const [value, setValue] = useState('')
  const [att, setAtt] = useState<Attachment | null>(initAtt || null)
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [hooked, setHooked] = useState<Record<number, boolean>>({})
  const [cards, setCards] = useState<Record<string, CardInfo>>({})
  const asked = useRef<Set<string>>(new Set())
  useEffect(() => {
    const need = new Set<string>()
    msgs.forEach((m) => {
      if (m.role !== 'bot') return
      if (m.r) (m.r.blocks || []).forEach((b: any) => { if (b.type === 'product_cards') b.items.forEach((p: any) => { if (!cards[p.product_id]) need.add(p.product_id) }) })
      ;(m.cards || []).forEach((p: any) => { if (!cards[p.product_id]) need.add(p.product_id) })
    })
    asked.current.forEach((x) => need.delete(x))
    if (!need.size) return
    need.forEach((x) => asked.current.add(x))
    api<{ cards: Record<string, CardInfo> }>('/api/home/cards?ids=' + [...need].slice(0, 12).join(',')).then((r) => setCards((c) => ({ ...c, ...r.cards }))).catch(() => {})
  }, [msgs]) // eslint-disable-line react-hooks/exhaustive-deps
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  useEffect(() => {   // newest message: short answers scroll fully into view; long ones show their start
    const el = scroller.current
    if (!el) return
    const run = () => {
      const all = el.querySelectorAll('.msg')
      const last = (all.length ? all[all.length - 1] : null) as HTMLElement | null
      if (!last) return
      const tall = last.offsetHeight > el.clientHeight - 24
      if (last.classList.contains('bot') && !last.classList.contains('pending') && tall) el.scrollTo({ top: last.offsetTop - 8, behavior: 'smooth' })
      else el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
    const t = window.setTimeout(run, 60)
    const t2 = window.setTimeout(run, 700)     // again after images / card info land
    return () => { window.clearTimeout(t); window.clearTimeout(t2) }
  }, [msgs.length, busy])
  useEffect(() => {   // keep the bottom visible when the footer (chips / attachment) changes height
    const el = scroller.current
    if (!el) return
    const onScroll = () => { pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40 }
    el.addEventListener('scroll', onScroll, { passive: true })
    const ro = new ResizeObserver(() => { if (pinned.current) el.scrollTop = el.scrollHeight })
    ro.observe(el)
    return () => { el.removeEventListener('scroll', onScroll); ro.disconnect() }
  }, [])
  const save = async (pid: string) => {
    try { const r: any = await api('/api/lists/items', { body: { cid: CID, product_id: pid } }); setSaved((s) => ({ ...s, [pid]: true })); toast(r.already_saved ? 'قبلاً در «لیست من» بود' : 'به «لیست من» اضافه شد') } catch (e) { toast(errText(e)) }
  }
  const hook = async (id: number, h: NonNullable<R['list_hook']>) => {
    try { await api('/api/lists/items', { body: { cid: CID, product_id: h.product_id, shop_id: h.shop_id, offer_id: h.offer_id } }); setHooked((s) => ({ ...s, [id]: true })); toast('به «لیست من» اضافه شد') } catch (e) { toast(errText(e)) }
  }
  const submit = () => {
    const t = value.trim()
    if (!t) { if (att) toast('یه توضیح کوتاه هم بنویس تا دنبالش بگردم'); return }
    onSend(t, att); setValue(''); setAtt(null)
  }
  const lastBot = [...msgs].reverse().find((m) => m.role === 'bot' && m.r) as Extract<Msg, { role: 'bot' }> | undefined
  const SELLER_Q = /فروشنده|فروشگاه|مغازه|کجا بخرم|از کجا|کی داره|کجا داره|کجا پیدا|بورس|کجا هست/
  const askedSellers = (id: number) => { const k = msgs.findIndex((x) => x.id === id); for (let j = k - 1; j >= 0; j--) { const u = msgs[j]; if (u.role === 'user') return SELLER_Q.test(u.text) } return false }
  const lastImgs: string[] = []
  ;(lastBot?.r?.blocks || []).forEach((b: any) => { if (b.type === 'product_cards') b.items.forEach((p: any) => p.image && lastImgs.push(p.image)) })
  return (
    <div className="screen-page chat">
      <div className="chat-h">
        <button className="chat-back" onClick={onBack} aria-label="بازگشت"><BackIcon /></button>
        <div className="segmented sm" data-active="chat">
          <span className="seg-pill" aria-hidden />
          <button className="seg-btn" aria-selected>چت</button>
          <button className="seg-btn" aria-selected={false} onClick={onTab}>نقشه</button>
        </div>
      </div>
      <div className="chat-scroll" ref={scroller}>
        {!msgs.length ? (
          <div className="chat-empty">
            <MascotAvatar state={mascot} size={84} />
            <h2>چی لازم داری؟</h2>
            <p>اسم کالا، بودجه یا محله‌ات را بنویس تا از بین فروشگاه‌های ترب برات پیدا کنم.</p>
          </div>
        ) : null}
        {msgs.map((m) => m.role === 'user' ? (
          <div className="msg user" key={m.id}>
            <div className="bubble-u">{m.att ? <img className="u-att" src={m.att.url} alt="" /> : null}<span>{m.text}</span></div>
            <span className="u-av"><UserIcon /></span>
          </div>
        ) : (
          <div className={'msg bot' + (m.pending ? ' pending' : '')} key={m.id}>
            {m.pending ? (
              <>
                {m.partial ? <div className="bot-row"><MascotAvatar state="think" size={46} /><div className="bubble-b streaming">{m.partial}</div></div>
                  : <div className="bot-row"><MascotAvatar state={m.stage === 'searching' ? 'search' : mascot} size={46} /><div className="bubble-b typing"><span>{STAGE[m.stage || ''] || (mascot === 'think' ? 'دارم فکر می‌کنم' : 'دارم می‌گردم')}{m.stage === 'searching' && m.nFound ? ` · ${m.nFound.toLocaleString('fa-IR')} کالا` : ''}</span><i /><i /><i /></div></div>}
                {m.cards?.length ? <div className="blk">{m.cards.map((p: any) => <ProductCard key={p.product_id} p={p} info={cards[p.product_id]} onOpen={onOpen} onSave={save} saved={!!saved[p.product_id]} />)}</div> : null}
              </>
            ) : m.error ? (
              <div className="bot-row"><MascotAvatar state="idle" size={46} /><div className="bubble-b">{m.error}{m.retry ? <button className="link-btn" onClick={() => onSend(m.retry!)}>دوباره بفرست</button> : null}</div></div>
            ) : m.r ? (
              <>
                {m.r.text ? <div className="bot-row"><MascotAvatar state="idle" size={46} /><div className="bubble-b">{m.r.text}</div></div> : null}
                <Blocks r={m.r} onOpen={onOpen} onShop={onShop} onSave={save} saved={saved} cards={cards} showSellers={askedSellers(m.id)} />
                {(() => {   // sellers block hidden by default: one small action that opens the product's sellers tab
                  const hasCards = (m.r.blocks || []).some((b: any) => b.type === 'product_cards')
                  const sb = (m.r.blocks || []).find((b: any) => b.type === 'sellers' && b.items?.length)
                  const pid = sb?.items?.find((o: any) => o.product_id)?.product_id
                  return sb && pid && !hasCards && !askedSellers(m.id) ? <button className="act-chip" onClick={() => onOpen(pid, 'sellers')}><Store /> فروشنده‌ها<span className="chev-c"><ChevLeft size={8} /></span></button> : null
                })()}
                {m.r.alternatives?.items?.length ? <div className="chat-alt"><AltBox r={m.r.alternatives} onShop={(sid, pid) => onShop(sid, pid)} /></div> : null}
                {m.r.project_result?.plans?.length ? <PlanUpdateCard pr={m.r.project_result} onOpen={onProject} /> : null}
                {(m.r.refine || []).map((q) => q.options?.length ? (   // questions that came WITH an answer: refinement chips (no sheet)
                  <div className="refine" key={q.id || q.title}><div className="refine-t">{q.title}</div>
                    <div className="refine-c" style={{ marginTop: -10 }}>{q.options.map((o) => <button key={o} className="act-chip" disabled={busy} onClick={() => { const a = { id: q.id || 'q', title: q.title, answer: o }; onSend(phrase(a), null, [a]) }}>{o}</button>)}</div></div>) : null)}
                {m.r.project && m.r.project.needs?.length ? <ProjectChecklist p={m.r.project} area={area} areaLabel={areaLabel} onSearched={onProject} /> : null}
                {m.r.bazaar && m.r.bazaar.hubs?.length ? <BazaarCard b={m.r.bazaar} onShop={onShop} /> : null}
                {m.r.list_hook && !hooked[m.id] && !(m.r.blocks || []).some((b: any) => b.type === 'product_cards') ? (
                  <button className="act-chip" onClick={() => hook(m.id, m.r!.list_hook!)}><Heart /> ذخیره</button>
                ) : null}
                {m.r.questions?.length ? <button className="act-chip" onClick={() => onQuestions(m.r!.questions!)}>{short(m.r.questions[0].title, 30)}<span className="chev-c"><ChevLeft size={8} /></span></button> : null}
              </>
            ) : null}
          </div>
        ))}
        <div style={{ height: 8 }} />
      </div>
      <div className="chat-foot">
        <div className="nchips">
          {(lastBot?.r?.suggestions || []).slice(0, 4).map((t) => (
            <button key={t} className="nchip" onClick={() => onSend(t)} disabled={busy}><Thumb text={t} imgs={lastImgs} /><span>{short(t, 26)}</span><span className="chev-c"><ChevLeft size={8} /></span></button>
          ))}
          {!(lastBot?.r?.suggestions || []).some((t) => /نزدیک/.test(t)) ? <button className="nchip" onClick={onArea}><span className="nthumb pin"><PinFill /></span><span>نزدیک {areaLabel}</span><span className="chev-c"><ChevLeft size={8} /></span></button> : null}
        </div>
        <Composer variant="chat" autoFocus={!msgs.length && !att} value={value} onChange={setValue} onSubmit={submit} placeholder="هر سوالی دربارهٔ خرید داری بپرس..." attachment={att} onAttach={setAtt} busy={busy} />
      </div>
    </div>
  )
}
