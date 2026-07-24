import { useEffect, useRef, useState } from 'react'

export interface TranscriptEntry {
  role: 'user' | 'assistant'
  text: string
  ts?: number
}

const POLL_INTERVAL_MS = 1500

/**
 * Polls GET /transcript on an interval and returns the latest list of
 * entries. Mirrors app.js's reset-on-shrink behavior: if the transcript
 * file was rotated/truncated (fewer entries than previously seen), the
 * list is replaced from scratch rather than appended.
 */
export function useTranscript(paused = false) {
  const [entries, setEntries] = useState<TranscriptEntry[]>([])
  const seenCountRef = useRef(0)
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  useEffect(() => {
    let cancelled = false

    async function poll() {
      if (pausedRef.current) return

      try {
        const res = await fetch('/transcript')
        const data = await res.json()
        if (cancelled || pausedRef.current || !Array.isArray(data)) return

        if (data.length < seenCountRef.current) {
          seenCountRef.current = 0
        }
        seenCountRef.current = data.length
        setEntries(data)
      } catch {
        // Ignore transient network errors; next poll will retry.
      }
    }

    poll()
    const id = window.setInterval(poll, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const clear = () => {
    seenCountRef.current = 0
    setEntries([])
  }

  const restore = (snapshot: TranscriptEntry[]) => {
    setEntries(snapshot)
    seenCountRef.current = snapshot.length
  }

  const append = (newEntries: TranscriptEntry[]) => {
    setEntries((prev) => {
      const next = [...prev, ...newEntries]
      seenCountRef.current = next.length
      return next
    })
  }

  return { entries, clear, restore, append }
}
