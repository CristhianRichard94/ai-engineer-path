import { useCallback, useRef, useState } from 'react'

export interface ConversationSummary {
  conversation_id: string
  first_ts: number
  last_ts: number
  turn_count: number
  preview: string
}

export type ConversationsStatus = 'idle' | 'loading' | 'error' | 'success'

/**
 * Fetches GET /conversations on demand (not automatically on mount) — the
 * History panel calls `refetch` when it opens. A request-id guard prevents
 * a slow, stale fetch from clobbering a newer one's result.
 */
export function useConversations() {
  const [status, setStatus] = useState<ConversationsStatus>('idle')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const requestIdRef = useRef(0)

  const refetch = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setStatus('loading')

    try {
      const res = await fetch('/conversations')
      if (!res.ok) throw new Error('Failed to load conversations')
      const data = await res.json()
      if (requestId !== requestIdRef.current) return
      if (!Array.isArray(data)) throw new Error('Unexpected response')
      setConversations(data)
      setStatus('success')
    } catch {
      if (requestId !== requestIdRef.current) return
      setStatus('error')
    }
  }, [])

  return { status, conversations, refetch }
}
