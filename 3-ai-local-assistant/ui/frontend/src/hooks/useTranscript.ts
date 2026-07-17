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
export function useTranscript() {
  const [entries, setEntries] = useState<TranscriptEntry[]>([])
  const seenCountRef = useRef(0)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await fetch('/transcript')
        const data = await res.json()
        if (cancelled || !Array.isArray(data)) return

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

  return entries
}
