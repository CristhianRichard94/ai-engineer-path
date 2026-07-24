import { useEffect, useRef, type KeyboardEvent } from 'react'
import type { TranscriptEntry } from '../hooks/useTranscript'
import type { ConversationViewStatus } from '../hooks/useConversationView'
import type { ResumeUiState } from '../hooks/useResumeConversation'
import { shortConversationLabel } from '../utils/historyFormat'

function roleLabel(role: string) {
  return role === 'user' ? 'user@jarvis:~$' : 'jarvis>'
}

interface HistoricalTranscriptPanelProps {
  status: ConversationViewStatus
  entries: TranscriptEntry[]
  conversationId: string
  firstTs?: number
  onBack: () => void
  onRetry: () => void
  resumeUiState: ResumeUiState
  resumeConfirmSecondsLeft: number
  onResumeClick: () => void
  onResumeKeyDown: (evt: KeyboardEvent<HTMLButtonElement>) => void
  resumeDisabled?: boolean
}

export default function HistoricalTranscriptPanel({
  status,
  entries,
  conversationId,
  firstTs,
  onBack,
  onRetry,
  resumeUiState,
  resumeConfirmSecondsLeft,
  onResumeClick,
  onResumeKeyDown,
  resumeDisabled = false,
}: HistoricalTranscriptPanelProps) {
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (entries.length > 0 && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [entries])

  const label = shortConversationLabel(conversationId, firstTs)
  const isResumeDisabled = resumeDisabled || resumeUiState === 'resuming'

  let resumeLabel: string
  let resumeAriaLabel: string | undefined
  if (resumeUiState === 'confirm-interrupt') {
    resumeLabel = `Confirm — interrupt JARVIS? (${resumeConfirmSecondsLeft})`
    resumeAriaLabel = `Confirm resume conversation, interrupting JARVIS, ${resumeConfirmSecondsLeft} seconds remaining`
  } else if (resumeUiState === 'resuming') {
    resumeLabel = 'Resuming…'
  } else {
    resumeLabel = 'Resume this Conversation'
  }

  return (
    <div
      id="history-panel"
      className="transcript-panel"
      role="region"
      aria-label="Conversation history"
      aria-describedby="history-banner-desc"
    >
      <div className="terminal-titlebar" aria-hidden="true">
        <span className="terminal-dot terminal-dot-red"></span>
        <span className="terminal-dot terminal-dot-amber"></span>
        <span className="terminal-dot terminal-dot-green"></span>
        <span className="terminal-title">jarvis@localhost:~/history/{label}</span>
      </div>
      <div className="history-banner" id="history-banner-desc">
        Viewing past conversation — not live.
      </div>

      {status === 'loading' && (
        <div className="history-log history-centered">
          <span className="restart-spinner" aria-hidden="true" />
          <span>Loading conversation…</span>
        </div>
      )}

      {status === 'error' && (
        <div className="history-log history-centered">
          <span className="history-error-text">Couldn't load this conversation.</span>
          <button type="button" className="history-retry-btn" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}

      {status === 'success' && (
        <div className="transcript-log" ref={logRef}>
          {entries.map((entry, i) => {
            const roleClass = entry.role === 'user' ? 'transcript-user' : 'transcript-assistant'
            return (
              <div key={i} className={`transcript-entry ${roleClass}`}>
                <span className="transcript-role">{roleLabel(entry.role)}</span>
                {String(entry.text || '')}
              </div>
            )
          })}
        </div>
      )}

      <div className="history-actions">
        <button type="button" className="history-back-btn" onClick={onBack}>
          Back to Live
        </button>
        <button
          type="button"
          className={`history-resume-btn state-${resumeUiState}`}
          disabled={isResumeDisabled || status !== 'success'}
          aria-label={resumeAriaLabel}
          onClick={onResumeClick}
          onKeyDown={onResumeKeyDown}
        >
          {resumeUiState === 'resuming' && (
            <span className="new-conversation-spinner" aria-hidden="true" />
          )}
          <span>{resumeLabel}</span>
        </button>
      </div>
    </div>
  )
}
