// Virtual try-on («پرو مجازی»): entry button + picker sheet + generating + result screens.
// Mount: <TryOnEntry product={{ product_id, title, image, min_price }} onCompare={() => setTab('sellers')} />
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { faNum, milNum, splitTitle } from '../fmt'
import { StatusBar } from '../StatusBar'
import { fetchEligibility, preparePhoto, runTryOn, TryOnError, type Eligibility, type TryOnMode, type TryOnResult } from './tryonApi'
import { BackIcon, CameraIcon, ChevLeft, CloseIcon, GalleryIcon, RetryIcon, ShareIcon, SparkIcon } from './icons'
import './tryon.css'

export type TryOnProduct = { product_id: string; title?: string | null; image?: string | null; min_price?: number | null }

const priceText = (p?: number | null) => (p ? (p >= 1e6 ? <>از <b>{milNum(p)}</b> میلیون تومان</> : <>از <b>{faNum(p)}</b> تومان</>) : null)
const fullPrice = (p?: number | null) => (p ? <>از <b>{faNum(p)}</b> تومان</> : null)

/** renders into the app's phone frame (.screen) so it sits above the product page regardless of scroll containers */
function Layer({ children }: { children: ReactNode }) {
  const host = (typeof document !== 'undefined' && (document.querySelector('.screen') as HTMLElement | null)) || document.body
  return createPortal(<div className="to-layer">{children}</div>, host)
}

/* ---------------------------------------------------------------- entry button */
export function TryOnButton({ el, onClick }: { el: Pick<Eligibility, 'kind' | 'cta'>; onClick: () => void }) {
  return (
    <button type="button" className={'to-entry ' + (el.kind === 'fashion' ? 'is-fashion' : 'is-home')} onClick={onClick}>
      <span className="to-entry-ic"><SparkIcon size={14} /></span>
      <span className="to-entry-t">{el.cta || (el.kind === 'fashion' ? 'روی عکس خودت امتحان کن' : 'در خانهٔ خودت امتحان کن')}</span>
    </button>
  )
}

/* ---------------------------------------------------------------- picker sheet */
export function TryOnPickSheet({ el, onClose, onFile, remaining, error }: {
  el: Eligibility; onClose: () => void; onFile: (f: File) => void; remaining?: number; error?: string | null
}) {
  const cam = useRef<HTMLInputElement>(null)
  const gal = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { const r = requestAnimationFrame(() => setOpen(true)); return () => cancelAnimationFrame(r) }, [])
  const pick = (f?: File | null) => { if (f) onFile(f) }
  const left = remaining ?? el.remaining
  return (
    <div className={'to-sheet-wrap' + (open ? ' open' : '')}>
      <div className="to-scrim" onClick={onClose} />
      <div className="to-sheet" role="dialog" aria-label="پرو مجازی">
        <div className="to-sheet-h">
          <div><h3>پرو مجازی</h3><p>{el.ask || (el.mode === 'person' ? 'یه عکس از خودت بده' : 'یه عکس از اتاقت بده')}</p></div>
          <button className="to-x" onClick={onClose} aria-label="بستن"><CloseIcon size={14} /></button>
        </div>
        <button className="to-opt" onClick={() => cam.current?.click()} disabled={left === 0}>
          <span className="to-opt-ic"><CameraIcon size={17} /></span><span className="to-opt-t">عکس بگیر</span><span className="to-chev"><ChevLeft size={9} /></span>
        </button>
        <i className="to-div" />
        <button className="to-opt" onClick={() => gal.current?.click()} disabled={left === 0}>
          <span className="to-opt-ic"><GalleryIcon size={17} /></span><span className="to-opt-t">انتخاب از گالری</span><span className="to-chev"><ChevLeft size={9} /></span>
        </button>
        {error ? <div className="to-sheet-err">{error}</div> : left === 0 ? <div className="to-sheet-err">سقف پرو مجازی برای این نشست پر شده است.</div>
          : typeof left === 'number' && left < 3 ? <div className="to-sheet-note">{faNum(left)} بار دیگر می‌توانی امتحان کنی</div> : null}
        <input ref={cam} type="file" accept="image/*" capture={el.mode === 'person' ? 'user' : 'environment'} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
        <input ref={gal} type="file" accept="image/*" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- generating */
export function TryOnGenerating({ photo, text, onCancel, error, onRetry, sbar = true }: {
  photo: string; text: string; onCancel: () => void; error?: string | null; onRetry?: () => void; sbar?: boolean
}) {
  return (
    <div className="to-page to-gen">
      <div className="to-sb">{sbar ? <StatusBar /> : null}</div>
      <div className="to-gen-main">
        <div className={'to-photo' + (error ? '' : ' is-busy')}><img src={photo} alt="" draggable={false} /></div>
        {error ? (
          <div className="to-gen-err"><b>{error}</b>{onRetry ? <button className="to-btn-ghost" onClick={onRetry}>یه عکس دیگه</button> : null}</div>
        ) : (
          <><div className="to-gen-t">{text}</div><div className="to-bar" role="progressbar" aria-label={text}><i /></div></>
        )}
      </div>
      <button className="to-cancel" onClick={onCancel}>{error ? 'بازگشت' : 'لغو'}</button>
    </div>
  )
}

/* ---------------------------------------------------------------- result */
export function TryOnResultView({ before, after, product, onBack, onRetry, onCompare, onShare, sbar = true, retryLeft }: {
  before: string; after: string; product: TryOnProduct; onBack: () => void; onRetry: () => void; onCompare: () => void; onShare: () => void; sbar?: boolean; retryLeft?: number
}) {
  const [side, setSide] = useState<'after' | 'before'>('after')
  const [faT] = splitTitle(product.title || '')
  return (
    <div className="to-page to-res">
      <div className="to-sb">{sbar ? <StatusBar /> : null}</div>
      <div className="to-res-top">
        <button className="to-circ" onClick={onBack} aria-label="بازگشت"><BackIcon /></button>
        <button className="to-circ" onClick={onShare} aria-label="اشتراک‌گذاری"><ShareIcon size={18} /></button>
      </div>
      <div className="to-res-scroll">
        <div className="to-photo to-res-ph">
          <img src={before} alt="قبل" className={side === 'before' ? 'on' : ''} draggable={false} />
          <img src={after} alt="بعد" className={side === 'after' ? 'on' : ''} draggable={false} />
          <div className="to-seg" role="tablist">
            <span className="to-seg-pill" style={{ transform: side === 'after' ? 'translateX(-100%)' : 'none' }} aria-hidden />
            <button role="tab" aria-selected={side === 'before'} onClick={() => setSide('before')}>قبل</button>
            <button role="tab" aria-selected={side === 'after'} onClick={() => setSide('after')}>بعد</button>
          </div>
        </div>
        <div className="to-cap">تصویر نمایشی با هوش مصنوعی</div>
        <button className="to-prow" onClick={onCompare}>
          <span className="to-prow-th">{product.image ? <img src={product.image} alt="" referrerPolicy="no-referrer" /> : null}</span>
          <span className="to-prow-c"><b>{faT || product.title}</b><small>{fullPrice(product.min_price)}</small></span>
          <span className="to-chev"><ChevLeft size={9} /></span>
        </button>
      </div>
      <div className="to-res-foot">
        <button className="to-cta" onClick={onCompare}>مقایسهٔ فروشنده‌ها</button>
        <button className="to-retry" onClick={onRetry} aria-label="امتحان با عکس دیگر" disabled={retryLeft === 0}><RetryIcon size={20} /></button>
      </div>
    </div>
  )
}

async function shareImage(url: string, title: string, toast?: (t: string) => void) {
  try {
    const blob = await (await fetch(url)).blob()
    const file = new File([blob], 'torob-tryon.jpg', { type: blob.type || 'image/jpeg' })
    const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean }
    if (nav.share && nav.canShare?.({ files: [file] })) { await nav.share({ files: [file], title, text: title }); return }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'torob-tryon.jpg'; a.click()
    toast?.('تصویر ذخیره شد')
  } catch (e) {
    if ((e as Error)?.name !== 'AbortError') toast?.('اشتراک‌گذاری ممکن نشد')
  }
}

/* ---------------------------------------------------------------- orchestrator */
type St = { k: 'idle' } | { k: 'pick'; err?: string | null } | { k: 'gen'; photo: string; err?: string | null } | { k: 'res'; photo: string; r: TryOnResult }

/** Self-contained try-on: fetches eligibility, renders the gradient entry button only for home/fashion products, and runs the whole flow. */
export function TryOnEntry({ product, onCompare, toast, sbar, eligibility }: {
  product: TryOnProduct; onCompare?: () => void; toast?: (t: string) => void; sbar?: boolean; eligibility?: Eligibility
}) {
  const [el, setEl] = useState<Eligibility | null>(eligibility || null)
  const [st, setSt] = useState<St>({ k: 'idle' })
  const [remaining, setRemaining] = useState<number | undefined>(eligibility?.remaining)
  const ac = useRef<AbortController | null>(null)
  const showSbar = sbar ?? (new URLSearchParams(location.search).has('statusbar') || window.matchMedia('(min-width: 560px) and (min-height: 700px)').matches)
  useEffect(() => {
    if (eligibility) return
    const a = new AbortController()
    fetchEligibility(product.product_id, a.signal).then((r) => { setEl(r); setRemaining(r.remaining) }).catch(() => setEl(null))
    return () => a.abort()
  }, [product.product_id, eligibility])
  useEffect(() => () => ac.current?.abort(), [])
  if (!el || !el.eligible || !el.mode) return null
  const mode = el.mode as TryOnMode
  const p: TryOnProduct = { ...product, title: product.title || el.title, image: product.image || el.image, min_price: product.min_price ?? el.min_price }

  const start = async (f: File) => {
    let prep: { blob: Blob; url: string }
    try { prep = await preparePhoto(f) } catch (e) { setSt({ k: 'pick', err: (e as Error).message }); return }
    setSt({ k: 'gen', photo: prep.url })
    ac.current?.abort(); const a = new AbortController(); ac.current = a
    try {
      const r = await runTryOn(p.product_id, mode, prep.blob, a.signal)
      setRemaining(r.remaining)
      const img = new Image(); img.src = r.image_url
      await img.decode().catch(() => {})
      if (!a.signal.aborted) setSt({ k: 'res', photo: prep.url, r })
    } catch (e) {
      if (e instanceof TryOnError && e.code === 'cancelled') return
      setSt({ k: 'gen', photo: prep.url, err: (e as Error).message || 'مشکلی پیش آمد؛ دوباره امتحان کن.' })
    }
  }
  const close = () => { ac.current?.abort(); setSt({ k: 'idle' }) }
  return (
    <>
      <TryOnButton el={el} onClick={() => setSt({ k: 'pick' })} />
      {st.k === 'pick' ? <Layer><TryOnPickSheet el={el} remaining={remaining} error={st.err} onClose={close} onFile={start} /></Layer> : null}
      {st.k === 'gen' ? <Layer><TryOnGenerating photo={st.photo} text={el.busy_text || 'دارم آماده‌اش می‌کنم…'} error={st.err} sbar={showSbar}
        onCancel={close} onRetry={() => setSt({ k: 'pick' })} /></Layer> : null}
      {st.k === 'res' ? <Layer><TryOnResultView before={st.photo} after={st.r.image_url} product={p} sbar={showSbar} retryLeft={remaining}
        onBack={close} onRetry={() => setSt({ k: 'pick' })} onShare={() => shareImage(st.r.image_url, p.title || 'پرو مجازی ترب', toast)}
        onCompare={() => { close(); onCompare?.() }} /></Layer> : null}
    </>
  )
}

export default TryOnEntry
export { priceText }
