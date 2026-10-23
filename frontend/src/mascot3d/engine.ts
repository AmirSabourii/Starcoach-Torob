/**
 * Procedural animation engine for the layered 3D Torob mascot.
 * Pure Web Animations API, framework-agnostic: React only renders the static skeleton and calls setState().
 *
 * Channels (nested, all with transform-origin at the feet):  carry > float > tilt > squash > react > poses
 *  - carry/shadowCarry : hand-off layer — absorbs the in-flight transform when the state changes and eases it to rest
 *  - float  : vertical float / hop        - tilt  : rocking / leaning
 *  - squash : breathing, squash & stretch - react : quick anticipation pulse on every state change
 */
import meta from './meta.json'

export type Mascot3DState = 'idle' | 'wave' | 'listen' | 'think' | 'search' | 'found'
export const MASCOT3D_STATES: Mascot3DState[] = ['idle', 'wave', 'listen', 'think', 'search', 'found']
const PROPS = ['qmark', 'check', 'dot1', 'dot2', 'dot3'] as const
type PropKey = (typeof PROPS)[number]

type Bbox = [number, number, number, number]
type PoseMeta = { pivot: [number, number]; feetBottom: number } & Partial<Record<PropKey, { bbox: Bbox }>>
const META = meta as unknown as { size: number; poses: Record<Mascot3DState, PoseMeta> }
const SZ = META.size

const urls = import.meta.glob('./assets/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>
const url = (name: string) => urls[`./assets/${name}.webp`]

const E = {
  out: 'cubic-bezier(.22,1,.36,1)',
  io: 'cubic-bezier(.45,0,.55,1)',
  inq: 'cubic-bezier(.55,0,1,.45)',
  back: 'cubic-bezier(.34,1.56,.64,1)',
  soft: 'cubic-bezier(.37,0,.63,1)',
}
const pct = (v: number) => ((v / SZ) * 100).toFixed(2) + '%'

type Pose = { el: HTMLDivElement; leaves: HTMLDivElement } & Partial<Record<PropKey, HTMLImageElement>>
export type Mascot3DRefs = {
  root: HTMLElement
  poses: HTMLElement
  carry: HTMLElement
  float: HTMLElement
  tilt: HTMLElement
  squash: HTMLElement
  react: HTMLElement
  shadowCarry: HTMLElement
  shadow: HTMLElement
  confetti: HTMLElement
}

/** Preload + decode every layer once per page (shared by all engine instances). */
let preloadPromise: Promise<void> | null = null
export function preloadMascot3D(): Promise<void> {
  if (!preloadPromise) {
    preloadPromise = Promise.all(
      Object.values(urls).map((u) => {
        const i = new Image()
        i.src = u
        return i.decode().catch(() => undefined)
      }),
    ).then(() => undefined)
  }
  return preloadPromise
}

export class Mascot3DEngine {
  private r: Mascot3DRefs
  private poses = {} as Record<Mascot3DState, Pose>
  private running: Animation[] = []
  private timers: number[] = []
  private cur: Mascot3DState | null = null
  private k: number // px amplitude scale (motion was tuned on a 300px stage)
  reduced: boolean

  constructor(refs: Mascot3DRefs, reduced: boolean) {
    this.r = refs
    this.reduced = reduced
    this.k = Math.max(0.8, refs.root.clientWidth / 300 || 1)
    for (const s of MASCOT3D_STATES) {
      const m = META.poses[s]
      const d = document.createElement('div')
      d.className = 'm3d-pose'
      d.appendChild(this.img(url(`${s}-body`)))
      const lv = document.createElement('div')
      lv.className = 'm3d-leaves'
      lv.style.transformOrigin = `${pct(m.pivot[0])} ${pct(m.pivot[1])}`
      lv.appendChild(this.img(url(`${s}-leaves`)))
      d.appendChild(lv)
      const p: Pose = { el: d, leaves: lv }
      for (const key of PROPS) {
        const pm = m[key]
        if (!pm) continue
        const b = pm.bbox
        const i = this.img(url(`${s}-${key}`))
        i.className = 'm3d-prop'
        // pivot: question mark -> bottom centre (its dot); check / typing dots -> centre
        const ox = (b[0] + b[2]) / 2
        const oy = key === 'qmark' ? b[3] : (b[1] + b[3]) / 2
        i.style.transformOrigin = `${pct(ox)} ${pct(oy)}`
        d.appendChild(i)
        p[key] = i
      }
      refs.poses.appendChild(d)
      this.poses[s] = p
    }
  }

  private img(src: string) {
    const i = new Image()
    i.decoding = 'async'
    i.src = src
    i.alt = ''
    i.draggable = false
    return i
  }

  destroy() {
    this.stopAll()
    this.timers.forEach((t) => clearTimeout(t))
    this.r.poses.innerHTML = ''
    this.r.confetti.innerHTML = ''
  }

  /* ---------- helpers ---------- */
  private px(v: number) {
    return (v * this.k).toFixed(2) + 'px'
  }
  private anim(node: Element, kf: Keyframe[], opt: KeyframeAnimationOptions) {
    const a = node.animate(kf, { fill: 'both', ...opt })
    this.running.push(a)
    return a
  }
  /** loop that must not hold its first frame during the delay (lets an intro animation show) */
  private loop(node: Element, kf: Keyframe[], opt: KeyframeAnimationOptions) {
    return this.anim(node, kf, { ...opt, fill: 'none', iterations: Infinity })
  }
  private stopAll() {
    for (const a of this.running) a.cancel()
    this.running = []
  }
  private tf(n: Element) {
    const t = getComputedStyle(n).transform
    return t === 'none' ? '' : t
  }
  private handoff(dur: number) {
    const { carry, float, tilt, squash, shadowCarry, shadow } = this.r
    const body = [this.tf(carry), this.tf(float), this.tf(tilt), this.tf(squash)].join(' ').trim() || 'none'
    const sh = [this.tf(shadowCarry), this.tf(shadow)].join(' ').trim() || 'none'
    const so = getComputedStyle(shadow).opacity
    carry.getAnimations().forEach((a) => a.cancel())
    shadowCarry.getAnimations().forEach((a) => a.cancel())
    this.stopAll()
    if (!dur) return
    carry.animate([{ transform: body }, { transform: 'none' }], { duration: dur, easing: E.out })
    shadowCarry.animate([{ transform: sh, opacity: so }, { transform: 'none', opacity: 1 }], { duration: dur, easing: E.out })
  }
  private freezeLeaves(p: Pose) {
    const t = this.tf(p.leaves)
    p.leaves.getAnimations().forEach((a) => a.cancel())
    if (t) {
      p.leaves.style.transform = t
      this.timers.push(window.setTimeout(() => { if (this.cur && this.poses[this.cur] !== p) p.leaves.style.transform = '' }, 400))
    }
  }
  private breathe(period = 3400, amp = 1) {
    const { squash, float, shadow } = this.r
    this.anim(squash, [{ transform: 'scale(1,1)' }, { transform: `scale(${1 - 0.01 * amp},${1 + 0.025 * amp})` }, { transform: 'scale(1,1)' }], { duration: period, iterations: Infinity, easing: E.soft })
    this.anim(float, [{ transform: 'translateY(0)' }, { transform: `translateY(-${this.px(4 * amp)})` }, { transform: 'translateY(0)' }], { duration: period * 1.25, iterations: Infinity, easing: E.soft })
    this.anim(shadow, [{ transform: 'scale(1)', opacity: 1 }, { transform: `scale(${1 - 0.06 * amp})`, opacity: 0.8 }, { transform: 'scale(1)', opacity: 1 }], { duration: period * 1.25, iterations: Infinity, easing: E.soft })
  }
  private leafSway(p: Pose, deg = 3, period = 3000, delay = 0) {
    this.anim(p.leaves, [{ transform: 'rotate(0deg)' }, { transform: `rotate(${-deg}deg)` }, { transform: 'rotate(0deg)' }, { transform: `rotate(${deg * 0.7}deg)` }, { transform: 'rotate(0deg)' }], { duration: period, iterations: Infinity, easing: E.soft, delay })
  }

  /* ---------- per-state motion ---------- */
  private motion: Record<Mascot3DState, (p: Pose) => void> = {
    idle: (p) => {
      this.breathe(3400, 1)
      this.leafSway(p, 2.5, 3800, 200)
    },

    wave: (p) => {
      const { squash, tilt, shadow, float } = this.r
      // anticipation dip -> pop -> rock twice around the feet -> settle
      this.anim(squash, [
        { transform: 'scale(1,1)', offset: 0 },
        { transform: 'scale(1.04,.94)', offset: 0.08, easing: E.out },
        { transform: 'scale(.98,1.04)', offset: 0.18, easing: E.out },
        { transform: 'scale(1,1)', offset: 0.3 },
        { transform: 'scale(1,1)', offset: 1 },
      ], { duration: 2200, easing: 'linear' })
      this.anim(tilt, [
        { transform: 'rotate(0deg)', offset: 0 }, { transform: 'rotate(0deg)', offset: 0.12 },
        { transform: 'rotate(-4deg)', offset: 0.26, easing: E.io }, { transform: 'rotate(4deg)', offset: 0.44, easing: E.io },
        { transform: 'rotate(-4deg)', offset: 0.62, easing: E.io }, { transform: 'rotate(3deg)', offset: 0.78, easing: E.io },
        { transform: 'rotate(0deg)', offset: 0.92, easing: E.out }, { transform: 'rotate(0deg)', offset: 1 },
      ], { duration: 2200, easing: 'linear' })
      // leaves: follow-through (lag + bigger amplitude)
      this.anim(p.leaves, [
        { transform: 'rotate(0deg)', offset: 0 }, { transform: 'rotate(-6deg)', offset: 0.16 },
        { transform: 'rotate(7deg)', offset: 0.33, easing: E.io }, { transform: 'rotate(-7deg)', offset: 0.51, easing: E.io },
        { transform: 'rotate(6deg)', offset: 0.69, easing: E.io }, { transform: 'rotate(-3deg)', offset: 0.85, easing: E.io },
        { transform: 'rotate(0deg)', offset: 1 },
      ], { duration: 2200, easing: 'linear' })
      this.anim(shadow, [
        { transform: 'scale(1)' }, { transform: 'scale(1.06,1)', offset: 0.08 }, { transform: 'scale(.98,1)', offset: 0.3 },
        { transform: 'scale(1.02,1)', offset: 0.5 }, { transform: 'scale(.98,1)', offset: 0.7 }, { transform: 'scale(1)' },
      ], { duration: 2200 })
      this.anim(float, [{ transform: 'translateY(0)' }, { transform: `translateY(-${this.px(3)})` }, { transform: 'translateY(0)' }], { duration: 4200, delay: 2200, iterations: Infinity, easing: E.soft })
    },

    listen: (p) => {
      const { squash, float, tilt, shadow } = this.r
      // eager lean-in pop with overshoot, then small springy bounces / nods while the user types
      this.anim(squash, [
        { transform: 'translateY(0) scale(1,1)' },
        { transform: 'translateY(1px) scale(1.05,.94)', offset: 0.22, easing: E.out },
        { transform: 'translateY(-2px) scale(1.01,1.06)', offset: 0.55, easing: E.out },
        { transform: 'translateY(2px) scale(1.03,1.015)' },
      ], { duration: 520, easing: 'linear' })
      this.anim(float, [
        { transform: 'translateY(0)' }, { transform: `translateY(-${this.px(5)})`, offset: 0.18, easing: E.out },
        { transform: 'translateY(0)', offset: 0.36, easing: E.inq }, { transform: `translateY(-${this.px(2.5)})`, offset: 0.5, easing: E.out },
        { transform: 'translateY(0)', offset: 0.64, easing: E.inq }, { transform: 'translateY(0)' },
      ], { duration: 1800, delay: 480, iterations: Infinity })
      this.anim(tilt, [
        { transform: 'rotate(0deg)' }, { transform: 'rotate(-2.5deg)', offset: 0.25, easing: E.io },
        { transform: 'rotate(0deg)', offset: 0.5, easing: E.io }, { transform: 'rotate(2.5deg)', offset: 0.75, easing: E.io },
        { transform: 'rotate(0deg)' },
      ], { duration: 3600, delay: 480, iterations: Infinity })
      this.anim(shadow, [
        { transform: 'scale(1)', opacity: 1 }, { transform: 'scale(.92)', opacity: 0.8, offset: 0.18 },
        { transform: 'scale(1)', opacity: 1, offset: 0.36 }, { transform: 'scale(.96)', opacity: 0.9, offset: 0.5 },
        { transform: 'scale(1)', opacity: 1, offset: 0.64 }, { transform: 'scale(1)', opacity: 1 },
      ], { duration: 1800, delay: 480, iterations: Infinity })
      // leaves perk: snap back, overshoot, then a fine eager tremble
      this.anim(p.leaves, [{ transform: 'rotate(0deg)' }, { transform: 'rotate(-10deg)', offset: 0.35, easing: E.out }, { transform: 'rotate(-3deg)', offset: 0.65, easing: E.io }, { transform: 'rotate(-6deg)' }], { duration: 560, easing: 'linear' })
      this.anim(p.leaves, [{ transform: 'rotate(-6deg)' }, { transform: 'rotate(-2.5deg)' }, { transform: 'rotate(-6deg)' }], { duration: 900, delay: 560, iterations: Infinity, easing: E.soft })
      // chat-style typing indicator: each dot pulses + fades in sequence (stagger 150 ms, 1.2 s loop)
      ;(['dot1', 'dot2', 'dot3'] as const).forEach((key, i) => {
        const d = p[key]
        if (!d) return
        this.anim(d, [{ opacity: 0, transform: 'scale(.4)' }, { opacity: 0.45, transform: 'scale(.8)' }], { duration: 240, delay: 180 + i * 70, easing: E.out })
        this.loop(d, [
          { opacity: 0.45, transform: 'scale(.8) translateY(0)' },
          { opacity: 1, transform: `scale(1.12) translateY(-${this.px(3)})`, offset: 0.22, easing: E.io },
          { opacity: 0.45, transform: 'scale(.8) translateY(0)', offset: 0.5 },
          { opacity: 0.45, transform: 'scale(.8) translateY(0)' },
        ], { duration: 1200, delay: 420 + i * 150, easing: E.soft })
      })
    },

    think: (p) => {
      const { squash, tilt, float } = this.r
      this.anim(squash, [{ transform: 'scale(.96,1.03)' }, { transform: 'scale(1.02,.99)', offset: 0.45 }, { transform: 'scale(1)' }], { duration: 520, easing: E.out })
      this.anim(tilt, [{ transform: 'rotate(0deg)' }, { transform: 'rotate(-3deg)' }, { transform: 'rotate(0deg)' }, { transform: 'rotate(3deg)' }, { transform: 'rotate(0deg)' }], { duration: 4400, iterations: Infinity, easing: E.soft, delay: 300 })
      this.anim(float, [{ transform: 'translateY(0)' }, { transform: `translateY(-${this.px(3)})` }, { transform: 'translateY(0)' }], { duration: 3000, iterations: Infinity, easing: E.soft, delay: 300 })
      this.leafSway(p, 2, 3600, 400)
      const q = p.qmark
      if (!q) return
      this.anim(q, [
        { opacity: 0, transform: 'translateY(10px) scale(.3) rotate(-20deg)' },
        { opacity: 1, transform: 'translateY(-4px) scale(1.12) rotate(6deg)', offset: 0.6 },
        { opacity: 1, transform: 'translateY(0) scale(1) rotate(0deg)' },
      ], { duration: 520, delay: 160, easing: E.out })
      this.loop(q, [
        { transform: 'translateY(0) rotate(0deg)' }, { transform: `translateY(-${this.px(6)}) rotate(-8deg)` },
        { transform: 'translateY(0) rotate(0deg)' }, { transform: `translateY(-${this.px(3)}) rotate(7deg)` },
        { transform: 'translateY(0) rotate(0deg)' },
      ], { duration: 2600, delay: 680, easing: E.soft })
      q.style.opacity = '1'
    },

    search: (p) => {
      const { tilt, shadow, squash } = this.r
      // slow scanning: lean + slide left/right (magnifier is baked into the body and moves with it)
      this.anim(tilt, [
        { transform: 'translateX(0) rotate(0deg)' }, { transform: `translateX(-${this.px(6)}) rotate(-4deg)`, offset: 0.25 },
        { transform: 'translateX(0) rotate(0deg)', offset: 0.5 }, { transform: `translateX(${this.px(6)}) rotate(4deg)`, offset: 0.75 },
        { transform: 'translateX(0) rotate(0deg)' },
      ], { duration: 2800, iterations: Infinity, easing: E.io })
      this.anim(shadow, [
        { transform: 'translateX(0) scale(1)' }, { transform: `translateX(-${this.px(4)}) scale(.97,1)`, offset: 0.25 },
        { transform: 'translateX(0) scale(1)', offset: 0.5 }, { transform: `translateX(${this.px(4)}) scale(.97,1)`, offset: 0.75 },
        { transform: 'translateX(0) scale(1)' },
      ], { duration: 2800, iterations: Infinity, easing: E.io })
      this.anim(p.leaves, [{ transform: 'rotate(0deg)' }, { transform: 'rotate(5deg)', offset: 0.3 }, { transform: 'rotate(0deg)', offset: 0.55 }, { transform: 'rotate(-5deg)', offset: 0.8 }, { transform: 'rotate(0deg)' }], { duration: 2800, iterations: Infinity, easing: E.io })
      this.anim(squash, [{ transform: 'scale(1,1)' }, { transform: 'scale(.995,1.012)' }, { transform: 'scale(1,1)' }], { duration: 1400, iterations: Infinity, easing: E.soft })
    },

    found: (p) => {
      const { squash, float, shadow, tilt } = this.r
      const D = 1100
      // anticipation squash -> stretch hop -> land squash -> settle
      this.anim(squash, [
        { transform: 'scale(1,1)', offset: 0 },
        { transform: 'scale(1.09,.90)', offset: 0.14, easing: E.out },
        { transform: 'scale(.94,1.08)', offset: 0.26, easing: E.out },
        { transform: 'scale(1,1)', offset: 0.42, easing: E.inq },
        { transform: 'scale(1.08,.92)', offset: 0.54, easing: E.out },
        { transform: 'scale(.98,1.02)', offset: 0.7, easing: E.io },
        { transform: 'scale(1,1)', offset: 1 },
      ], { duration: D, easing: 'linear' })
      this.anim(float, [
        { transform: 'translateY(0)', offset: 0 }, { transform: 'translateY(0)', offset: 0.16 },
        { transform: `translateY(-${this.px(18)})`, offset: 0.36, easing: E.inq },
        { transform: 'translateY(0)', offset: 0.53 }, { transform: 'translateY(0)', offset: 1 },
      ], { duration: D, easing: E.out })
      this.anim(shadow, [
        { transform: 'scale(1)', opacity: 1, offset: 0 }, { transform: 'scale(1.08,1)', opacity: 1, offset: 0.14 },
        { transform: 'scale(.72)', opacity: 0.45, offset: 0.36 }, { transform: 'scale(1.1,1)', opacity: 1, offset: 0.54 },
        { transform: 'scale(1)', opacity: 1, offset: 1 },
      ], { duration: D })
      this.anim(p.leaves, [
        { transform: 'rotate(0deg)', offset: 0 }, { transform: 'rotate(6deg)', offset: 0.2 }, { transform: 'rotate(-8deg)', offset: 0.4 },
        { transform: 'rotate(9deg)', offset: 0.6 }, { transform: 'rotate(-4deg)', offset: 0.78 }, { transform: 'rotate(0deg)', offset: 1 },
      ], { duration: D + 200, easing: E.io })
      this.anim(tilt, [{ transform: 'scale(1)' }, { transform: 'scale(1.008,1.016)' }, { transform: 'scale(1)' }], { duration: 2600, delay: D, iterations: Infinity, easing: E.soft })
      const c = p.check
      if (c) {
        this.anim(c, [
          { opacity: 0, transform: 'scale(0) rotate(-25deg)' }, { opacity: 1, transform: 'scale(1.28) rotate(8deg)', offset: 0.55 },
          { opacity: 1, transform: 'scale(.94) rotate(-2deg)', offset: 0.8 }, { opacity: 1, transform: 'scale(1) rotate(0deg)' },
        ], { duration: 560, delay: 380, easing: E.out })
        this.loop(c, [{ transform: 'translateY(0)' }, { transform: `translateY(-${this.px(4)})` }, { transform: 'translateY(0)' }], { duration: 1800, delay: 940, easing: E.soft })
        c.style.opacity = '1'
      }
      this.timers.push(window.setTimeout(() => { if (this.cur === 'found') this.confetti() }, 400))
    },
  }

  /** small brand-colour dots that burst from behind the body and fade */
  private confetti() {
    if (this.reduced) return
    const box = this.r.confetti
    const S = this.r.root.clientWidth
    const cols = ['#6BAF8D', '#8FCBAA', '#F2836B', '#F6B6C8', '#C9B8F2']
    for (let i = 0; i < 16; i++) {
      const s = document.createElement('span')
      const a = ((-160 + i * (140 / 15)) * Math.PI) / 180 + (Math.random() - 0.5) * 0.25
      const r = (S / 300) * (95 + Math.random() * 60)
      const x0 = S / 2, y0 = S * 0.39
      const sz = 3.5 + Math.random() * 4.5
      s.style.background = cols[i % cols.length]
      s.style.width = s.style.height = sz + 'px'
      if (i % 4 === 0) { s.style.borderRadius = '2px'; s.style.height = sz * 0.55 + 'px' }
      box.appendChild(s)
      const dx = Math.cos(a) * r, dy = Math.sin(a) * r
      s.animate([
        { transform: `translate(${x0}px,${y0}px) scale(.2)`, opacity: 0 },
        { transform: `translate(${x0 + dx * 0.7}px,${y0 + dy * 0.7}px) scale(1) rotate(90deg)`, opacity: 1, offset: 0.35 },
        { transform: `translate(${x0 + dx}px,${y0 + dy + 30}px) scale(.8) rotate(200deg)`, opacity: 0 },
      ], { duration: 1150 + Math.random() * 350, easing: 'cubic-bezier(.15,.7,.35,1)', fill: 'forwards' }).finished.then(() => s.remove(), () => s.remove())
    }
  }

  /* ---------- state machine entry point ---------- */
  setState(s: Mascot3DState, instant = false) {
    if (s === this.cur) return
    const prev = this.cur ? this.poses[this.cur] : null
    const next = this.poses[s]
    // props first: snapshot their live opacity/transform so the outgoing ones can fade from where they are
    for (const key of PROPS) {
      for (const st of MASCOT3D_STATES) {
        const pr = this.poses[st][key]
        if (!pr || st === s) continue
        const cs = getComputedStyle(pr)
        const op = +cs.opacity, tr = cs.transform
        pr.getAnimations().forEach((a) => a.cancel())
        if (op > 0.01 && prev === this.poses[st] && !this.reduced) {
          pr.animate([{ opacity: op, transform: tr }, { opacity: 0, transform: tr }], { duration: 160 })
        }
        pr.style.opacity = '0'
        pr.style.transform = ''
      }
      const np = next[key]
      if (np) np.style.opacity = '0'
    }
    if (prev) this.freezeLeaves(prev)
    this.handoff(instant || this.reduced ? 0 : 340)
    next.leaves.style.transform = ''
    this.cur = s
    const XF = 200
    if (instant || !prev || this.reduced) {
      for (const st of MASCOT3D_STATES) {
        const pe = this.poses[st].el
        pe.getAnimations().forEach((a) => a.cancel())
        pe.classList.toggle('is-on', st === s)
        pe.style.zIndex = ''
      }
    } else {
      // anticipation + "dissolve-over": the incoming pose fades in ON TOP of the fully opaque outgoing one
      // (so the ring never turns translucent), then the outgoing pose fades away.
      this.r.react.animate([
        { transform: 'scale(1)' }, { transform: 'scale(.97)', offset: 0.4, easing: E.inq },
        { transform: 'scale(1.012)', offset: 0.75, easing: E.out }, { transform: 'scale(1)' },
      ], { duration: 360 })
      for (const st of MASCOT3D_STATES) {
        const pe = this.poses[st].el
        if (pe !== prev.el && pe !== next.el) {
          pe.getAnimations().forEach((a) => a.cancel())
          pe.classList.remove('is-on')
          pe.style.zIndex = ''
        }
      }
      next.el.getAnimations().forEach((a) => a.cancel())
      prev.el.style.zIndex = '1'
      next.el.style.zIndex = '2'
      next.el.classList.add('is-on')
      next.el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: XF, easing: 'cubic-bezier(.33,0,.2,1)' })
      const fo = prev.el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 150, delay: XF - 30, easing: E.io, fill: 'forwards' })
      fo.finished.then(() => {
        if (this.poses[this.cur!] !== prev) { prev.el.classList.remove('is-on'); prev.el.style.zIndex = '' }
        fo.cancel()
      }, () => undefined)
    }
    if (this.reduced) {
      for (const key of PROPS) { const np = next[key]; if (np) np.style.opacity = '1' }
      return
    }
    this.motion[s](next)
  }
}
