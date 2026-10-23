import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Mascot3D } from './mascot3d/Mascot3D'
import type { MascotState } from './useMascot'
import { Close, Plus, Send } from './icons'
import { fa, faNum, short, UNKNOWN } from './fmt'

/** small animated mascot (same layered 3D engine as the home hero) clipped into a round avatar */
export function MascotAvatar({ state, size = 40, onTap }: { state: MascotState; size?: number; onTap?: () => void }) {
  return (
    <span className="m-avatar" style={{ width: size, height: size }}>
      <span className="m-avatar-box" style={{ width: size * 1.32, height: size * 1.32, marginLeft: -size * 0.66, top: size * 0.04 }}>
        <Mascot3D state={state} onTap={onTap || (() => {})} />
      </span>
    </span>
  )
}

/** assistant mascot state for chat: think → search while a request is in flight, found when it lands, then idle */
export function useAssistantState(busy: boolean, doneTick: number): MascotState {
  const [st, setSt] = useState<MascotState>('idle')
  useEffect(() => {
    if (!busy) return
    setSt('think')
    const t = window.setTimeout(() => setSt('search'), 1600)
    return () => window.clearTimeout(t)
  }, [busy])
  useEffect(() => {
    if (!doneTick) return
    setSt('found')
    const t = window.setTimeout(() => setSt('idle'), 2200)
    return () => window.clearTimeout(t)
  }, [doneTick])
  return busy ? (st === 'found' || st === 'idle' ? 'think' : st) : st
}

export type Attachment = { name: string; url: string }

/** chat/search input. The ＋ (attach photo) button sits on the RIGHT (RTL start side) of the text field. */
export function Composer({ value, onChange, onSubmit, placeholder, attachment, onAttach, onFocus, onBlur, variant = 'chat', busy, autoFocus, end }: {
  value: string; onChange: (v: string) => void; onSubmit: () => void; placeholder: string
  attachment: Attachment | null; onAttach: (a: Attachment | null) => void
  onFocus?: () => void; onBlur?: () => void; variant?: 'home' | 'chat'; busy?: boolean; autoFocus?: boolean; end?: ReactNode
}) {
  const file = useRef<HTMLInputElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)
  useEffect(() => { if (autoFocus) input.current?.focus() }, [autoFocus])
  const pick = (f: File | undefined) => {
    if (!f) return
    onAttach({ name: f.name, url: URL.createObjectURL(f) })
  }
  return (
    <form className={`composer composer-${variant}` + (focused ? ' is-focused' : '') + (attachment ? ' has-att' : '')}
      onSubmit={(e) => { e.preventDefault(); if (!busy) { input.current?.blur(); onSubmit() } }}>
      {attachment && (
        <div className="att-chip">
          <img src={attachment.url} alt="" />
          <span className="att-name">{short(attachment.name, 22)}</span>
          <button type="button" className="att-x" aria-label="حذف عکس" onClick={() => onAttach(null)}><Close /></button>
        </div>
      )}
      <div className="composer-inner">
        <button type="button" className="composer-plus" aria-label="افزودن عکس یا فایل" onClick={() => file.current?.click()}>
          <Plus />
        </button>
        <span className="composer-divider" aria-hidden />
        <input ref={input} className="composer-input" value={value} placeholder={placeholder} enterKeyHint="send" autoComplete="off"
          onFocus={() => { setFocused(true); onFocus?.() }} onBlur={() => { setFocused(false); onBlur?.() }}
          onChange={(e) => onChange(e.target.value)} />
        {variant === 'chat' && value.trim() ? (
          <button type="submit" className="composer-send" aria-label="ارسال" disabled={busy}><Send /></button>
        ) : variant === 'chat' && end ? <span className="composer-end">{end}</span> : null}
        <input ref={file} type="file" accept="image/*" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
      </div>
    </form>
  )
}

export function Sheet({ children, onClose, className = '', full }: { children: ReactNode; onClose: () => void; className?: string; full?: boolean }) {
  const [open, setOpen] = useState(false)
  useEffect(() => { const r = requestAnimationFrame(() => setOpen(true)); return () => cancelAnimationFrame(r) }, [])
  return (
    <div className={'sheet-wrap' + (open ? ' open' : '')}>
      <div className="sheet-scrim" onClick={onClose} />
      <div className={'sheet ' + (full ? 'sheet-full ' : '') + className} role="dialog">
        <div className="sheet-grab" aria-hidden />
        {children}
      </div>
    </div>
  )
}

export function Toast({ text }: { text: string | null }) {
  return <div className={'toast' + (text ? ' on' : '')} role="status">{text}</div>
}

export function Img({ src, alt = '', className = '' }: { src?: string | null; alt?: string; className?: string }) {
  const [bad, setBad] = useState(false)
  if (!src || bad) return <span className={'img-ph ' + className} aria-hidden />
  return <img className={className} src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setBad(true)} draggable={false} />
}

export type GridProduct = {
  product_id: string; title: string; image: string | null; n_shops: number
  price: { price_toman: number | null; fresh: boolean; labels: string[] }
  discount_pct?: number
}
export function ProductTile({ p, onOpen, wide }: { p: GridProduct; onOpen: (pid: string) => void; wide?: boolean }) {
  return (
    <button type="button" className={'ptile' + (wide ? ' wide' : '')} onClick={() => onOpen(p.product_id)}>
      <span className="ptile-im"><Img src={p.image} />{p.discount_pct ? <span className="ptile-badge">{fa(p.discount_pct)}٪ زیر میانه</span> : null}</span>
      <span className="ptile-t">{short(p.title, 64)}</span>
      <span className="ptile-p">{p.price.price_toman ? <>از <b>{faNum(p.price.price_toman)}</b> تومان</> : <b className="unk">{UNKNOWN}</b>}</span>
      <span className="ptile-s">{fa(p.n_shops)} فروشنده{p.price.labels?.includes('قدیمی') ? <span className="flag stale">قدیمی</span> : null}</span>
    </button>
  )
}

export function Spinner() { return <span className="spinner" aria-hidden /> }
