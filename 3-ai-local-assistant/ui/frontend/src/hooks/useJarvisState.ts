import { useCallback, useEffect, useRef, useState } from 'react'

export interface JarvisStatePayload {
  state: string
  detail: string
  amplitude?: number
}

/**
 * Connects to the /state SSE endpoint and keeps the latest {state, detail}
 * in React state. Reconnects with a 1.5s backoff on error, same as the
 * original vanilla app.js implementation.
 */
export function useJarvisState() {
  const [state, setState] = useState('off')
  const [detail, setDetail] = useState('')
  const [amplitude, setAmplitude] = useState<number | undefined>(undefined)
  const [connected, setConnected] = useState(true)

  const applyState = useCallback((nextState: string, nextDetail: string, nextAmplitude?: number) => {
    setState(nextState || 'off')
    setDetail(nextDetail || '')
    setAmplitude(typeof nextAmplitude === 'number' ? nextAmplitude : undefined)
  }, [])

  const esRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)

  useEffect(() => {
    function connect() {
      if (esRef.current) {
        esRef.current.close()
      }
      const es = new EventSource('/state')
      esRef.current = es

      es.onmessage = (evt) => {
        setConnected(true)
        try {
          const data = JSON.parse(evt.data)
          applyState(data.state || 'off', data.detail || '', data.amplitude)
        } catch {
          // ignore malformed payloads
        }
      }

      es.onerror = () => {
        setConnected(false)
        es.close()
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = window.setTimeout(connect, 1500)
      }
    }

    connect()

    return () => {
      if (esRef.current) esRef.current.close()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    }
  }, [applyState])

  return { state, detail, amplitude, connected, applyState }
}
