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
  // Server-side transcript.jsonl is now a permanent append-only log (it's no
  // longer truncated on "New Conversation" - see /new-conversation). For
  // callers with no conversation_id (the voice loop never tags its own
  // entries), GET /transcript can't scope to "only entries since the last
  // clear" server-side, so we enforce that boundary here: any entry with
  // ts <= this cutoff is filtered out of what the poller shows, even though
  // it's still physically in the file.
  const clearedAfterRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      if (pausedRef.current) return

      try {
        const res = await fetch('/transcript')
        const data = await res.json()
        if (cancelled || pausedRef.current || !Array.isArray(data)) return

        const cutoff = clearedAfterRef.current
        const visible = cutoff === null ? data : data.filter((e) => (e.ts ?? 0) > cutoff)

        if (visible.length < seenCountRef.current) {
          seenCountRef.current = 0
        }
        seenCountRef.current = visible.length
        setEntries(visible)
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
    clearedAfterRef.current = Date.now() / 1000
    seenCountRef.current = 0
    setEntries([])
  }

  const restore = (snapshot: TranscriptEntry[], opts: { liftCutoff?: boolean } = {}) => {
    // liftCutoff is only true for a genuine resume (commitResume) - that's
    // the one case where showing older, already-cleared entries is correct.
    // Rolling back a failed clear, or backing out of history without
    // resuming, must NOT lift the cutoff: doing so silently resurrects
    // entries the user already cleared on the next poll.
    if (opts.liftCutoff) {
      clearedAfterRef.current = null
    }
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
