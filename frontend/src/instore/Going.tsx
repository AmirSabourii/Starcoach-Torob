// «مقصد فعلی»: the shop the shopper said they're going to (localStorage), its MallGuide story, the home entry, and the saved-items header button. $0, no model.
import { useEffect, useState } from 'react'
import { api, CID } from '../api'
import { fa, faNum, short } from '../fmt'
import { Close, Heart } from '../icons'
import { Img, MascotAvatar, Sheet } from '../ui'
import { MallGuideStory } from '../mallguide/MallGuide'
import { getGuide, type Guide } from '../mallguide/mallguideApi'

export type Dest = { shop_id: string; product_id?: string | null; name: string; ts: number; mall?: string | null; where?: string | null; route?: string | null; in_mall?: boolean }
const KEY = 'torob.dest'
export function getDest(): Dest | null {     // stored per spec-going.md: {shopId,name,mallId,floor,unit,setAt} (+ productId, where, route, inMall)
  try {
    const d = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (!d || !d.shopId) return null
    if (Date.now() - d.setAt > 24 * 3600e3) { localStorage.removeItem(KEY); return null }
    return { shop_id: d.shopId, product_id: d.productId || null, name: d.name, ts: d.setAt, mall: d.mallId || null, where: d.where || null, route: d.route || null, in_mall: !!d.inMall }
  } catch { return null }
}
export function setDest(d: Omit<Dest, 'ts'> & { floor?: string | null; unit?: string | null }) {
  localStorage.setItem(KEY, JSON.stringify({ shopId: d.shop_id, name: d.name, mallId: d.mall || null, floor: d.floor || null, unit: d.unit || null, setAt: Date.now(),
    productId: d.product_id || null, where: d.where || null, route: d.route || null, inMall: !!d.in_mall }))
  window.dispatchEvent(new Event('dest-change'))
}
export function clearDest() { localStorage.removeItem(KEY); window.dispatchEvent(new Event('dest-change')) }
export function useDest() {
  const [d, setD] = useState<Dest | null>(getDest)
  useEffect(() => { const f = () => setD(getDest()); window.addEventListener('dest-change', f); window.addEventListener('storage', f); return () => { window.removeEventListener('dest-change', f); window.removeEventListener('storage', f) } }, [])
  return d
}

/** opens the MallGuide story for a shop (DB guide only, no web lookup); not in a mall -> onNotMall() */
export function GoingStory({ sid, pid, sbar, onClose, onNotMall, onAsk, onContact }: {
  sid: string; pid?: string | null; sbar?: boolean; onClose: () => void; onNotMall?: () => void; onAsk?: () => void; onContact?: () => void
}) {
  const [g, setG] = useState<Guide | null>(null)
  useEffect(() => {
    let a = true
    getGuide(sid, pid).then((r) => { if (!a) return; if (r?.eligible) setG(r); else { onNotMall?.(); onClose() } }).catch(() => { if (a) { onNotMall?.(); onClose() } })
    return () => { a = false }
  }, [sid, pid]) // eslint-disable-line react-hooks/exhaustive-deps
  return g ? <MallGuideStory guide={g} sbar={sbar} onClose={onClose} onAsk={onAsk} onContact={onContact} /> : null
}

/** home: «داری می‌ری» card while a destination is set */
export function GoingEntry({ sbar }: { sbar?: boolean; onShop?: (sid: string, pid?: string | null) => void }) {
  const d = useDest()
  const [story, setStory] = useState(false)
  if (!d) return null
  return (
    <>
      <div className="go-entry">
        <MascotAvatar state="idle" size={36} />
        <span className="go-tx"><b>داری می‌ری {short(d.name, 22)}</b><small>{d.in_mall ? [d.mall, d.where].filter(Boolean).join('، ') : 'نامشخص'}</small></span>
        {d.in_mall ? <button className="go-act" onClick={() => setStory(true)}>راهنما</button>
          : d.route ? <a className="go-act" href={d.route} target="_blank" rel="noreferrer">مسیر</a> : null}
        <button className="go-x" aria-label="بستن" onClick={clearDest}><Close /></button>
      </div>
      {story ? <GoingStory sid={d.shop_id} pid={d.product_id} sbar={sbar} onClose={() => setStory(false)} /> : null}
    </>
  )
}

/** shop sheet: after «می‌رم اینجا» — map routing, and the mall guide only when the shop is in a mall with floor/unit */
export function GoingSheet({ sid, pid, name, route, onClose, onGuide, toast }: {
  sid: string; pid?: string | null; name: string; route?: string | null; onClose: () => void; onGuide: () => void; toast: (t: string) => void
}) {
  const [g, setG] = useState<Guide | null | undefined>(undefined)
  useEffect(() => {
    let a = true
    getGuide(sid, pid).then((r) => { if (!a) return; setG(r)
      const inMall = !!(r?.eligible && (r.floor || r.unit))
      setDest({ shop_id: sid, product_id: pid || null, name, in_mall: inMall, mall: r?.mall || null, floor: r?.floor?.label || null, unit: r?.unit?.label || null, where: [r?.floor?.label, r?.unit?.label].filter(Boolean).join('، ') || null, route: route || null })
    }).catch(() => { if (a) { setG(null); setDest({ shop_id: sid, product_id: pid || null, name, in_mall: false, route: route || null }) } })
    toast('مقصدت شد ' + name)
    return () => { a = false }
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps
  const inMall = !!(g?.eligible && (g.floor || g.unit))
  return (
    <Sheet onClose={onClose} className="go-sheet">
      {route ? <a className="go-row" href={route} target="_blank" rel="noreferrer" onClick={onClose}><b>مسیریابی با نقشه</b><small>نشان، بلد یا گوگل‌مپ</small></a> : null}
      {inMall ? <button className="go-row" onClick={() => { onClose(); onGuide() }}><b>راهنمای داخل پاساژ</b><small>{[g?.mall, g?.floor?.label, g?.unit?.label].filter(Boolean).join('، ')}</small></button> : null}
    </Sheet>
  )
}

type Item = { item_id: string; product_id: string; title: string; image: string | null; snap_price: number | null; shop_name: string | null }
/** home header: saved items with a count badge -> one sheet with the saved lists' items */
export function SavedButton({ onOpen }: { onOpen: (pid: string) => void }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [open, setOpen] = useState(false)
  const load = () => api<{ lists: { name: string; items: Item[] }[] }>('/api/lists?cid=' + encodeURIComponent(CID)).then((r) => setItems(r.lists.flatMap((l) => l.items || []))).catch(() => setItems([]))
  useEffect(() => { load() }, [])
  useEffect(() => { if (open) load() }, [open])
  const n = items?.length || 0
  return (
    <>
      <button className="go-saved" aria-label="ذخیره‌شده‌ها" onClick={() => setOpen(true)}><Heart />{n ? <span className="go-badge">{n > 99 ? fa(99) + '+' : fa(n)}</span> : null}</button>
      {open ? (
        <Sheet onClose={() => setOpen(false)} className="go-sheet">
          <h3 className="go-h">ذخیره‌شده‌ها</h3>
          {!items ? null : items.length ? items.map((it) => (
            <button key={it.item_id} className="go-item" onClick={() => { setOpen(false); onOpen(it.product_id) }}>
              <span className="go-im"><Img src={it.image} /></span>
              <span className="go-t"><b>{short(it.title, 48)}</b><small>{it.shop_name || 'نامشخص'}</small></span>
              <span className="go-p">{it.snap_price ? faNum(it.snap_price) : 'نامشخص'}</span>
            </button>
          )) : <p className="go-empty">هنوز چیزی ذخیره نکردی</p>}
        </Sheet>) : null}
    </>
  )
}
