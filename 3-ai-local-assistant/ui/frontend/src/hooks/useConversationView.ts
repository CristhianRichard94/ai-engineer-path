import { useCallback, useRef, useState } from 'react'
import type { TranscriptEntry } from './useTranscript'

export type ConversationViewStatus = 'idle' | 'loading' | 'error' | 'success'

/**
 * One-shot (not polled) fetch of GET /transcript?conversation_id=<id> for
 * viewing a single past conversation read-only. Call `load(conversationId)`
 * to fetch; a request-id guard prevents a stale response from a previous
 * `load` call from clobbering a newer one.
 */
export function useConversationView() {
  const [status, setStatus] = useState<ConversationViewStatus>('idle')
  const [entries, setEntries] = useState<TranscriptEntry[]>([])
  const requestIdRef = useRef(0)

  const load = useCallback(async (conversationId: string) => {
    const requestId = ++requestIdRef.current
    setStatus('loading')

    try {
      const res = await fetch(`/transcript?conversation_id=${encodeURIComponent(conversationId)}`)
      if (!res.ok) throw new Error('Failed to load conversation')
      const data = await res.json()
      if (requestId !== requestIdRef.current) return
      if (!Array.isArray(data)) throw new Error('Unexpected response')
      setEntries(data)
      setStatus('success')
    } catch {
      if (requestId !== requestIdRef.current) return
      setStatus('error')
    }
  }, [])

  const reset = useCallback(() => {
    requestIdRef.current++
    setStatus('idle')
    setEntries([])
  }, [])

  return { status, entries, load, reset }
}
