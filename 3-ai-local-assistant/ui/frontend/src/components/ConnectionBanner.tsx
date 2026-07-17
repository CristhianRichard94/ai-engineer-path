import { useEffect, useRef, useState } from 'react'

type Phase = 'hidden' | 'entering' | 'shown' | 'exiting'

export default function ConnectionBanner({ connected }: { connected: boolean }) {
  const [phase, setPhase] = useState<Phase>('hidden')
  const timerRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (!connected) {
      if (phase === 'hidden' || phase === 'exiting') {
        if (timerRef.current) {
          clearTimeout(timerRef.current)
          timerRef.current = null
        }
        setPhase('entering')
        rafRef.current = requestAnimationFrame(() => setPhase('shown'))
      }
    } else if (phase === 'entering' || phase === 'shown') {
      setPhase('exiting')
      timerRef.current = window.setTimeout(() => setPhase('hidden'), 200)
    }

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  if (phase === 'hidden') return null

  return (
    <div
      id="connection-banner"
      className={`connection-banner ${phase === 'entering' ? 'entering' : ''} ${phase === 'exiting' ? 'exiting' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="dot" aria-hidden="true">●</span>
      <span>Lost connection to JARVIS &mdash; retrying&hellip;</span>
    </div>
  )
}
