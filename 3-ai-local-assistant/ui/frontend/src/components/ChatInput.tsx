import { useRef, useState, type KeyboardEvent } from 'react'
import { useChat } from '../hooks/useChat'

interface ChatInputProps {
  viewingHistory?: boolean
  pendingResumeId?: string | null
  onResumeSuccess?: (conversationId: string) => void
}

export default function ChatInput({
  viewingHistory = false,
  pendingResumeId = null,
  onResumeSuccess,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const { sending, error, sendMessage } = useChat(pendingResumeId, onResumeSuccess)
  // React state (`sending`) isn't synchronously readable across two fast
  // events fired before a re-render commits, so a ref guard is needed to
  // reliably prevent a double-submit (e.g. two near-simultaneous Enter
  // presses, or Enter + click). This ref is checked-and-set synchronously
  // at the very top of submit(), before any async work starts.
  const submittingRef = useRef(false)

  const submit = async () => {
    if (submittingRef.current) return
    if (!value.trim() || sending || viewingHistory) return

    submittingRef.current = true
    const message = value
    setValue('')
    try {
      await sendMessage(message)
    } finally {
      submittingRef.current = false
    }
  }

  const handleKeyDown = (evt: KeyboardEvent<HTMLInputElement>) => {
    if (evt.key === 'Enter' && !evt.shiftKey) {
      evt.preventDefault()
      submit()
    }
  }

  return (
    <div id="chat-input-wrapper" className="chat-input-wrapper">
      <div className="chat-input-row">
        <input
          type="text"
          id="chat-input"
          className="chat-input"
          placeholder={viewingHistory ? 'Resume this conversation to continue it.' : 'Type a message to JARVIS…'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={sending || viewingHistory}
          aria-label="Message JARVIS"
        />
        <button
          type="button"
          id="chat-send-btn"
          className="chat-send-btn"
          onClick={submit}
          disabled={sending || viewingHistory || !value.trim()}
        >
          {sending ? <span className="chat-send-spinner" aria-hidden="true" /> : 'Send'}
        </button>
      </div>
      {error && (
        <div className="chat-input-error" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
