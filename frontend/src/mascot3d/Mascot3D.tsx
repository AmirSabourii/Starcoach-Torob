import { useEffect, useRef, useState } from 'react'
import { Mascot3DEngine, preloadMascot3D, type Mascot3DRefs, type Mascot3DState } from './engine'
import './mascot3d.css'

function usePrefersReducedMotion() {
  const q = '(prefers-reduced-motion: reduce)'
  const [reduced, setReduced] = useState(() => window.matchMedia?.(q).matches ?? false)
  useEffect(() => {
    const m = window.matchMedia(q)
    const fn = () => setReduced(m.matches)
    m.addEventListener('change', fn)
    return () => m.removeEventListener('change', fn)
  }, [])
  return reduced
}

/**
 * Layered 3D mascot. React renders a static skeleton once; all motion is driven imperatively by
 * Mascot3DEngine (Web Animations API) so state changes never re-render or remount image layers.
 */
export function Mascot3D({ state, onTap }: { state: Mascot3DState; onTap: () => void }) {
  const reduced = usePrefersReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  const poses = useRef<HTMLDivElement>(null)
  const carry = useRef<HTMLDivElement>(null)
  const float = useRef<HTMLDivElement>(null)
  const tilt = useRef<HTMLDivElement>(null)
  const squash = useRef<HTMLDivElement>(null)
  const react = useRef<HTMLDivElement>(null)
  const shadowCarry = useRef<HTMLDivElement>(null)
  const shadow = useRef<HTMLDivElement>(null)
  const confetti = useRef<HTMLDivElement>(null)
  const engine = useRef<Mascot3DEngine | null>(null)
  const latest = useRef(state)
  latest.current = state
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const refs = { root, poses, carry, float, tilt, squash, react, shadowCarry, shadow, confetti }
    const r = Object.fromEntries(Object.entries(refs).map(([k, v]) => [k, v.current])) as unknown as Mascot3DRefs
    const e = new Mascot3DEngine(r, reduced)
    engine.current = e
    let alive = true
    preloadMascot3D().then(() => {
      if (!alive) return
      e.setState(latest.current, true)
      setReady(true)
    })
    return () => {
      alive = false
      e.destroy()
      engine.current = null
    }
    // the engine is rebuilt only when the reduced-motion preference flips
  }, [reduced])

  useEffect(() => {
    if (ready) engine.current?.setState(state)
  }, [state, ready])

  return (
    <div className={'m3d' + (ready ? ' is-ready' : '')} ref={root} data-state={state}>
      <div className="m3d-ch" ref={shadowCarry} aria-hidden>
        <div className="m3d-shadow" ref={shadow} />
      </div>
      <div className="m3d-ch" ref={carry} aria-hidden>
        <div className="m3d-ch" ref={float}>
          <div className="m3d-ch" ref={tilt}>
            <div className="m3d-ch" ref={squash}>
              <div className="m3d-ch" ref={react}>
                <div className="m3d-poses" ref={poses} />
                <div className="m3d-confetti" ref={confetti} />
              </div>
            </div>
          </div>
        </div>
      </div>
      <button type="button" className="m3d-hit" onClick={onTap} aria-label="ماسکات ترب" />
    </div>
  )
}
