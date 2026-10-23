import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Mascot3D } from './mascot3d/Mascot3D'
import { useMascot } from './useMascot'
import { Chevron, ChevLeft, Pin, Plus, Spark } from './icons'
import { Composer, MascotAvatar, ProductTile, type Attachment, type GridProduct } from './ui'
import { LiveMap } from './LiveMap'
import { StatusBar } from './StatusBar'
import phone from './assets/thumbs/phone.png'
import headphones from './assets/thumbs/headphones.png'
import pin from './assets/thumbs/pin.png'
import laptop from './assets/thumbs/laptop.png'
import cDigital from './assets/cat/c-digital.png'
import cHome from './assets/cat/c-home.png'
import cFashion from './assets/cat/c-fashion.png'
import cSport from './assets/cat/c-sport.png'
import cBeauty from './assets/cat/c-beauty.png'
import cToys from './assets/cat/c-toys.png'
import cBooks from './assets/cat/c-books.png'
import cTools from './assets/cat/c-tools.png'

type Suggestion = { id: string; l1: string; l2: string; img: string; tone: string; q: string }
// RTL grid: first item lands top-right (same order as the reference)
const SUGGESTIONS: Suggestion[] = [
  { id: 'phone', l1: 'گوشی مناسب', l2: 'عکاسی تا ۲۰ میلیون', img: phone, tone: 'lavender', q: 'گوشی مناسب عکاسی تا ۲۰ میلیون' },
  { id: 'headphones', l1: 'یه هدفون بی‌سیم', l2: 'تا ۳ میلیون', img: headphones, tone: 'grey', q: 'یه هدفون بی‌سیم تا ۳ میلیون' },
  { id: 'pin', l1: 'نزدیک‌ترین', l2: 'فروشگاه‌های ونک', img: pin, tone: 'pink', q: 'نزدیک‌ترین فروشگاه‌های ونک' },
  { id: 'laptop', l1: 'لپ‌تاپ سبک', l2: 'برای دانشجو', img: laptop, tone: 'lavender', q: 'لپ‌تاپ سبک برای دانشجو' },
]
export const TILES = [
  { key: 'digital', label: 'کالای دیجیتال', img: cDigital, c: 'c1' },
  { key: 'home', label: 'خانه و آشپزخانه', img: cHome, c: 'c2' },
  { key: 'fashion', label: 'مد و پوشاک', img: cFashion, c: 'c3' },
  { key: 'sport', label: 'ورزش و سفر', img: cSport, c: 'c4' },
  { key: 'beauty', label: 'زیبایی و سلامت', img: cBeauty, c: 'c5' },
  { key: 'kids', label: 'اسباب‌بازی و کودک', img: cToys, c: 'c6' },
  { key: 'books', label: 'کتاب و لوازم تحریر', img: cBooks, c: 'c7' },
  { key: 'tools', label: 'ابزار و ساختمان', img: cTools, c: 'c8' },
]

export function Home({ tab, setTab, onAsk, onAskShop, onTile, onDeals, onOpen, onShop, area, areaLabel, onArea, deals, sbar }: {
  tab: 'chat' | 'map'; setTab: (t: 'chat' | 'map') => void; onAsk: (q: string, att?: Attachment | null) => void; onAskShop?: (sid: string, name: string) => void
  onTile: (key: string, label: string) => void; onDeals: () => void; onOpen: (pid: string) => void; onShop: (sid: string) => void
  area: string; areaLabel: string; onArea: () => void; deals: GridProduct[] | null; sbar: boolean
}) {
  const [value, setValue] = useState('')
  const [att, setAtt] = useState<Attachment | null>(null)
  const mascot = useMascot()
  const scroller = useRef<HTMLDivElement>(null)
  const hdrFile = useRef<HTMLInputElement>(null)
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const on = () => setCompact(el.scrollTop > 470)
    on(); el.addEventListener('scroll', on, { passive: true })
    return () => el.removeEventListener('scroll', on)
  }, [tab])
  const submit = () => {
    const t = value.trim()
    if (!t) return
    mascot.submit(); onAsk(t, att); setValue(''); setAtt(null)
  }
  const ask = (q: string) => { mascot.submit(); onAsk(q) }
  return (
    <div className="screen-page home" data-mascot={mascot.state}>
      <div className={'sticky' + (compact && tab === 'chat' ? ' on' : '')} aria-hidden={!compact}>
        <div className="sb-space">{sbar ? <StatusBar /> : null}</div>
        <div className="hdr">
          <button className="avatar" onClick={() => scroller.current?.scrollTo({ top: 0, behavior: 'smooth' })} aria-label="بالای صفحه">
            <MascotAvatar state={mascot.state} size={40} />
          </button>
          <button className="ask" onClick={() => onAsk('')}>
            <span className="plus" role="button" aria-label="افزودن عکس" onClick={(e) => { e.stopPropagation(); hdrFile.current?.click() }}><Plus size={11} /></span>
            <span className="ph">از دستیار ترب بپرس...</span>
            <span className="spark"><Spark /></span>
          </button>
          <input ref={hdrFile} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onAsk('', { name: f.name, url: URL.createObjectURL(f) }) }} />
          <button className="loc" onClick={onArea}>
            <Pin />
            <span className="t"><small>نزدیک</small>{areaLabel}</span>
          </button>
        </div>
      </div>

      <div className="home-scroll" ref={scroller}>
        <div className="sb-space">{sbar ? <StatusBar /> : null}</div>
        <div className="segmented" role="tablist" data-active={tab}>
          <span className="seg-pill" aria-hidden />
          <button role="tab" aria-selected={tab === 'chat'} className="seg-btn" onClick={() => setTab('chat')}>چت</button>
          <button role="tab" aria-selected={tab === 'map'} className="seg-btn" onClick={() => setTab('map')}>نقشه</button>
        </div>

        {tab === 'map' ? (
          <LiveMap area={area} areaLabel={areaLabel} onShop={onShop} onArea={onArea} onAsk={(q) => onAsk(q)} onAskShop={(sid, name) => (onAskShop ? onAskShop(sid, name) : onAsk(`دربارهٔ «${name}» بگو`))} />
        ) : (
          <>
            <div className="mascot-stage">
              <div className="mascot-glow" aria-hidden />
              <div className="mascot-floor" aria-hidden />
              <div className="mascot3d-box"><Mascot3D state={mascot.state} onTap={mascot.greet} /></div>
            </div>
            <h1 className="title">امروز دنبال چی می‌گردی؟</h1>
            <p className="subtitle">با هوش مصنوعی ترب، راحت‌تر و هوشمندتر خرید کن.</p>
            <Composer variant="home" value={value} placeholder="هر چیزی برای خرید می‌خواهی بنویس..." attachment={att} onAttach={setAtt}
              onChange={(v) => { setValue(v); mascot.onType() }} onSubmit={submit} onFocus={mascot.onFocus} onBlur={mascot.onBlur} />
            <section className="cards">
              {SUGGESTIONS.map((s) => (
                <button key={s.id} type="button" className="card" onClick={() => ask(s.q)}>
                  <span className="card-chev"><Chevron /></span>
                  <span className="card-text"><span>{s.l1}</span><span>{s.l2}</span></span>
                  <span className={'card-thumb tone-' + s.tone}><img src={s.img} alt="" draggable={false} /></span>
                </button>
              ))}
            </section>

            <div className="explore">
              <div className="intro">
                <h2>دنیایی از<br />محصولات پیش روی شما</h2>
                <p>دسته‌بندی‌های متنوع را ببینید<br />و بهترین گزینه را پیدا کنید.</p>
              </div>
              <div className="tiles">
                {TILES.map((t) => (
                  <button key={t.key} className={'tile ' + t.c} onClick={() => onTile(t.key, t.label)}>
                    <img src={t.img} alt="" draggable={false} />
                    <span className="chev"><ChevLeft /></span>
                    <span className="lb">{t.label}</span>
                  </button>
                ))}
              </div>
              <div className="sec">
                <div className="sec-h"><h2>کم‌قیمت‌ترین پیشنهادهای امروز</h2><button onClick={onDeals}>همه</button></div>
                <div className="deals">
                  {deals === null ? [0, 1].map((i) => <div key={i} className="ptile skel"><span className="ptile-im" /></div>)
                    : deals.slice(0, 6).map((p) => <ProductTile key={p.product_id} p={p} onOpen={onOpen} />)}
                </div>
              </div>
              <div style={{ height: 40 }} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
export { api }
