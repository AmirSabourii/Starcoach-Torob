import { useEffect, useState } from 'react'
import { api, errText } from './api'
import { clean, fa } from './fmt'
import { BackIcon } from './icons'
import { MascotAvatar, ProductTile, Sheet, type GridProduct } from './ui'

type Cat = { key: string; label: string; total: number; subs: { name: string; n_products: number }[]; items: GridProduct[] }

export function CategoryScreen({ tkey, label, onBack, onOpen }: { tkey: string; label: string; onBack: () => void; onOpen: (pid: string) => void }) {
  const [sub, setSub] = useState<string | null>(null)
  const [data, setData] = useState<Cat | null>(null)
  const [items, setItems] = useState<GridProduct[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = async (offset: number) => {
    setLoading(true); setErr(null)
    try {
      const qs = new URLSearchParams({ offset: String(offset), limit: '20' })
      if (sub) qs.set('sub', sub)
      const r = await api<Cat>(`/api/home/category/${tkey}?` + qs.toString())
      setData(r); setItems((x) => (offset ? [...x, ...r.items] : r.items))
    } catch (e) { setErr(errText(e)) } finally { setLoading(false) }
  }
  useEffect(() => { setItems([]); load(0) }, [tkey, sub]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="screen-page listing">
      <div className="page-h"><button className="icon-btn" onClick={onBack} aria-label="بازگشت"><BackIcon /></button><h1>{label}</h1><span style={{ width: 36 }} /></div>
      {data?.subs?.length ? (
        <div className="subs">
          <button className={'fchip' + (!sub ? ' on' : '')} onClick={() => setSub(null)}>همه</button>
          {data.subs.map((s) => <button key={s.name} className={'fchip' + (sub === s.name ? ' on' : '')} onClick={() => setSub(s.name)}>{clean(s.name)} <small>{fa(s.n_products)}</small></button>)}
        </div>
      ) : null}
      <div className="page-scroll">
        {data ? <p className="muted-p">{fa(data.total)} کالا · مرتب‌شده بر اساس تعداد فروشنده</p> : null}
        {err ? <div className="empty"><MascotAvatar state="think" size={64} /><p>{err}</p><button className="btn-dark" onClick={() => load(0)}>تلاش دوباره</button></div> : null}
        {data && data.total === 0 ? <div className="empty"><MascotAvatar state="idle" size={64} /><p>فعلاً کالایی در این دسته ثبت نشده است.</p></div> : null}
        <div className="grid2">{items.map((p) => <ProductTile key={p.product_id} p={p} onOpen={onOpen} />)}</div>
        {!data && !err ? <div className="empty"><MascotAvatar state="search" size={64} /><p>در حال آوردن کالاها…</p></div> : null}
        {data && items.length < data.total ? <button className="link-btn center" disabled={loading} onClick={() => load(items.length)}>{loading ? 'صبر کن…' : 'نمایش بیشتر'}</button> : null}
        <div style={{ height: 30 }} />
      </div>
    </div>
  )
}

export function DealsScreen({ onBack, onOpen }: { onBack: () => void; onOpen: (pid: string) => void }) {
  const [d, setD] = useState<{ items: GridProduct[]; rule: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api<any>('/api/home/deals?limit=40').then(setD).catch((e) => setErr(errText(e))) }, [])
  return (
    <div className="screen-page listing">
      <div className="page-h"><button className="icon-btn" onClick={onBack} aria-label="بازگشت"><BackIcon /></button><h1>کم‌قیمت‌ترین پیشنهادهای امروز</h1><span style={{ width: 36 }} /></div>
      <div className="page-scroll">
        {d ? <p className="muted-p">قیمت به‌روز هر کالا در مقایسه با میانهٔ قیمت همان کالا</p> : null}
        {err ? <div className="empty"><p>{err}</p></div> : null}
        {!d && !err ? <div className="empty"><MascotAvatar state="search" size={64} /><p>در حال آوردن پیشنهادها…</p></div> : null}
        <div className="grid2">{d?.items.map((p) => <ProductTile key={p.product_id} p={p} onOpen={onOpen} />)}</div>
        <div style={{ height: 30 }} />
      </div>
    </div>
  )
}

export type Area = { key: string; label: string; lat: number; lon: number }
export function AreaSheet({ areas, cur, onPick, onClose }: { areas: Area[]; cur: string; onPick: (a: Area) => void; onClose: () => void }) {
  return (
    <Sheet onClose={onClose} className="area-sheet">
      <h3 className="sheet-t">محدودهٔ خرید در تهران</h3>
      <p className="sheet-p">فروشگاه‌های نزدیک، نقشه و «خرید یکجا» از این محدوده شروع می‌شوند.</p>
      <div className="area-grid">
        {areas.map((a) => <button key={a.key} className={'fchip' + (a.key === cur ? ' on' : '')} onClick={() => onPick(a)}>{a.label}</button>)}
      </div>
    </Sheet>
  )
}
