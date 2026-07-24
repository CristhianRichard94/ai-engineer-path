import type { ConversationSummary, ConversationsStatus } from '../hooks/useConversations'
import { formatShortDate, rowMetaTime } from '../utils/historyFormat'

interface HistoryListPanelProps {
  status: ConversationsStatus
  conversations: ConversationSummary[]
  activeConversationId: string | null
  onSelect: (conversation: ConversationSummary) => void
  onRetry: () => void
}

export default function HistoryListPanel({
  status,
  conversations,
  activeConversationId,
  onSelect,
  onRetry,
}: HistoryListPanelProps) {
  const sorted = [...conversations].sort((a, b) => b.last_ts - a.last_ts)

  return (
    <div
      id="history-panel"
      className="transcript-panel"
      role="region"
      aria-label="Conversation history"
    >
      <div className="terminal-titlebar" aria-hidden="true">
        <span className="terminal-dot terminal-dot-red"></span>
        <span className="terminal-dot terminal-dot-amber"></span>
        <span className="terminal-dot terminal-dot-green"></span>
        <span className="terminal-title">jarvis@localhost:~/history</span>
      </div>

      {status === 'loading' && (
        <div className="history-log history-centered">
          <span className="restart-spinner" aria-hidden="true" />
          <span>Loading conversations…</span>
        </div>
      )}

      {status === 'error' && (
        <div className="history-log history-centered">
          <span className="history-error-text">Couldn't load conversation history.</span>
          <button type="button" className="history-retry-btn" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}

      {status === 'success' && sorted.length === 0 && (
        <div className="history-log">
          <div className="transcript-entry history-empty-entry">No past conversations yet.</div>
        </div>
      )}

      {status === 'success' && sorted.length > 0 && (
        <div className="history-log">
          <div role="list">
            {sorted.map((conv) => {
              const preview = conv.preview && conv.preview.trim()
              const previewText = preview ? preview : `(no preview) — ${formatShortDate(conv.first_ts)}`
              const isCurrent = conv.conversation_id === activeConversationId
              return (
                <button
                  key={conv.conversation_id}
                  type="button"
                  role="listitem"
                  className="history-row"
                  onClick={() => onSelect(conv)}
                >
                  <span className="history-row-preview">{previewText}</span>
                  <span className="history-row-meta">
                    {isCurrent && <span className="history-current-tag">current</span>}
                    <span className="history-row-time">{rowMetaTime(conv.last_ts, conv.turn_count)}</span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
