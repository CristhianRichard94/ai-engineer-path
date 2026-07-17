import { useEffect, useRef, useState } from 'react'

const STATUS_TEXT: Record<string, string | null> = {
  off: 'JARVIS is offline.',
  wake_listening: 'Listening for wake word.',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
  error: null, // uses detail
  restarting: 'Restarting…',
}

function useTakingLonger(state: string) {
  const [showLonger, setShowLonger] = useState(false)
  const sinceRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (state === 'thinking') {
      if (sinceRef.current === null) {
        sinceRef.current = Date.now()
        setShowLonger(false)
        timerRef.current = window.setTimeout(() => setShowLonger(true), 5000)
      }
    } else {
      sinceRef.current = null
      setShowLonger(false)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [state])

  return showLonger
}

interface StatusTextProps {
  state: string
  detail: string
  override: string | null
}

export default function StatusText({ state, detail, override }: StatusTextProps) {
  const showLonger = useTakingLonger(state)

  if (override) {
    return (
      <p id="status-text" role="status" aria-live="polite">
        {override}
      </p>
    )
  }

  if (state === 'thinking') {
    return (
      <p id="status-text" role="status" aria-live="polite">
        {STATUS_TEXT.thinking}
        {showLonger && <span className="taking-longer"> (taking longer than usual)</span>}
      </p>
    )
  }

  if (state === 'error') {
    const text = detail ? String(detail).slice(0, 200) : 'An error occurred, sir.'
    return (
      <p id="status-text" className="error" role="status" aria-live="assertive">
        {text}
      </p>
    )
  }

  return (
    <p id="status-text" role="status" aria-live="polite">
      {STATUS_TEXT[state] || ''}
    </p>
  )
}
