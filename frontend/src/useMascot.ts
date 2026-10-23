import { useCallback, useEffect, useRef, useState } from 'react'
import { MASCOT3D_STATES, type Mascot3DState } from './mascot3d/engine'

export type MascotState = Mascot3DState
export const MASCOT_STATES = MASCOT3D_STATES

export const GREET_MS = 2500
export const THINK_MS = 1600
export const SEARCH_MS = 2200
export const FOUND_MS = 2200

type Step = { state: MascotState; ms: number }

/**
 * Mascot state machine.
 *  - ambient: idle, or listen while the composer is focused / being typed in
 *  - sequence: app-load greeting, mascot tap (wave), submit (think → search → found); always ends back on ambient
 *  - forced: ?debug=1 switcher overrides everything
 */
export function useMascot() {
  const [focused, setFocused] = useState(false)
  const [seqState, setSeqState] = useState<MascotState | null>('wave')
  const [forced, setForced] = useState<MascotState | null>(null)
  const timers = useRef<number[]>([])

  const clearSeq = () => {
    timers.current.forEach((t) => window.clearTimeout(t))
    timers.current = []
  }

  const runSequence = useCallback((steps: Step[]) => {
    clearSeq()
    let at = 0
    steps.forEach((s) => {
      timers.current.push(window.setTimeout(() => setSeqState(s.state), at))
      at += s.ms
    })
    timers.current.push(
      window.setTimeout(() => {
        timers.current = []
        setSeqState(null)
      }, at),
    )
  }, [])

  const cancelSequence = useCallback(() => {
    clearSeq()
    setSeqState(null)
  }, [])

  // app load → greeting once → idle
  useEffect(() => {
    runSequence([{ state: 'wave', ms: GREET_MS }])
    return clearSeq
  }, [runSequence])

  /** Enter / suggestion card: think → search → found → idle (mascot reaction only, no fake results) */
  const submit = useCallback(() => {
    runSequence([
      { state: 'think', ms: THINK_MS },
      { state: 'search', ms: SEARCH_MS },
      { state: 'found', ms: FOUND_MS },
    ])
  }, [runSequence])

  /** Tap on the mascot: greeting once → idle */
  const greet = useCallback(() => runSequence([{ state: 'wave', ms: GREET_MS }]), [runSequence])

  const onFocus = useCallback(() => {
    setFocused(true)
    cancelSequence() // the user is about to type: follow them
  }, [cancelSequence])

  const onBlur = useCallback(() => setFocused(false), [])

  const onType = useCallback(() => {
    if (timers.current.length) cancelSequence()
  }, [cancelSequence])

  const ambient: MascotState = focused ? 'listen' : 'idle'
  const state: MascotState = forced ?? seqState ?? ambient
  return { state, forced, setForced, submit, greet, onFocus, onBlur, onType }
}
