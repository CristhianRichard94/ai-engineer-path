import { useRef, useState } from 'react'

interface ChatResponse {
  reply?: string
  intent?: string
  error?: string
}

/**
 * Drives the text-chat input: posts a message to POST /chat.
 *
 * Does NOT append the resulting turns to the transcript client-side -
 * transcript.jsonl (written server-side by POST /chat before it responds)
 * is the single source of truth, and the existing poll-based transcript
 * viewer (useTranscript) will surface the new lines on its own next cycle.
 * Appending here too would race the poller and double-render the turns
 * when a request takes longer than the poll interval.
 *
 * `pendingResumeId`, when set, is attached as `conversation_id` on the
 * *next* sendMessage call only — the backend resumes that conversation
 * server-side as a side effect of that one request. It's only cleared
 * (via `onResumeSuccess`) once that request actually succeeds, so the
 * caller can commit the resumed conversation as "active". If the request
 * fails, `pendingResumeId` is left untouched (both here and by the caller)
 * so the very next send attempt retries the resume with the same
 * `conversation_id` instead of silently creating a new conversation.
 */
export function useChat(
  pendingResumeId: string | null = null,
  onResumeSuccess?: (conversationId: string) => void
) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pendingResumeIdRef = useRef(pendingResumeId)
  pendingResumeIdRef.current = pendingResumeId

  const sendMessage = async (message: string) => {
    const trimmed = message.trim()
    if (!trimmed || sending) return

    setSending(true)
    setError(null)

    const resumeId = pendingResumeIdRef.current

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resumeId ? { message: trimmed, conversation_id: resumeId } : { message: trimmed }),
      })

      const data: ChatResponse = await res.json().catch(() => ({}))

      if (!res.ok || data.error || typeof data.reply !== 'string') {
        setError(data.error || 'Failed to send message.')
        // Leave resumeId in place (both the ref and the caller's state) so
        // the next attempt retries the resume with the same conversation_id.
        return
      }

      if (resumeId) {
        pendingResumeIdRef.current = null
        onResumeSuccess?.(resumeId)
      }
    } catch {
      setError('Failed to reach JARVIS. Please try again.')
      // Same as above: keep resumeId for a retry.
    } finally {
      setSending(false)
    }
  }

  return { sending, error, sendMessage }
}
