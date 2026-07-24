import { useState } from 'react'

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
 */
export function useChat() {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = async (message: string) => {
    const trimmed = message.trim()
    if (!trimmed || sending) return

    setSending(true)
    setError(null)

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed }),
      })

      const data: ChatResponse = await res.json().catch(() => ({}))

      if (!res.ok || data.error || typeof data.reply !== 'string') {
        setError(data.error || 'Failed to send message.')
      }
    } catch {
      setError('Failed to reach JARVIS. Please try again.')
    } finally {
      setSending(false)
    }
  }

  return { sending, error, sendMessage }
}
