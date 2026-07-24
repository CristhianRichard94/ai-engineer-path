import type { KeyboardEvent } from 'react'
import type { NewConversationUiState } from '../hooks/useNewConversation'

interface NewConversationButtonProps {
  uiState: NewConversationUiState
  confirmSecondsLeft: number
  onClick: () => void
  onKeyDown: (evt: KeyboardEvent<HTMLButtonElement>) => void
  disabled?: boolean
}

export default function NewConversationButton({
  uiState,
  confirmSecondsLeft,
  onClick,
  onKeyDown,
  disabled = false,
}: NewConversationButtonProps) {
  const className = `new-conversation-btn state-${uiState}`
  const isDisabled = disabled || uiState === 'clearing'

  let label: string
  let ariaLabel: string | undefined
  if (uiState === 'confirm-interrupt') {
    label = `Confirm — interrupt JARVIS? (${confirmSecondsLeft})`
    ariaLabel = `Confirm clear conversation, interrupting JARVIS, ${confirmSecondsLeft} seconds remaining`
  } else if (uiState === 'clearing') {
    label = 'Clearing…'
  } else {
    label = 'New Conversation'
  }

  return (
    <div id="new-conversation-wrapper">
      <button
        id="new-conversation-btn"
        className={className}
        type="button"
        disabled={isDisabled}
        aria-label={ariaLabel}
        onClick={onClick}
        onKeyDown={onKeyDown}
      >
        {uiState === 'clearing' && <span className="new-conversation-spinner" aria-hidden="true" />}
        <span className="new-conversation-btn-label">{label}</span>
      </button>
    </div>
  )
}
