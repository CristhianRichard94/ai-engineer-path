import type { KeyboardEvent } from 'react'
import type { RestartUiState } from '../hooks/useRestart'

interface RestartButtonProps {
  uiState: RestartUiState
  confirmSecondsLeft: number
  onClick: () => void
  onKeyDown: (evt: KeyboardEvent<HTMLButtonElement>) => void
  disabled?: boolean
}

export default function RestartButton({
  uiState,
  confirmSecondsLeft,
  onClick,
  onKeyDown,
  disabled: externalDisabled = false,
}: RestartButtonProps) {
  const className = `restart-btn state-${uiState}`
  const disabled = externalDisabled || uiState === 'restarting'

  let label: string
  let ariaLabel: string | undefined
  if (uiState === 'confirm') {
    label = `Confirm restart? (${confirmSecondsLeft})`
    ariaLabel = `Confirm restart, ${confirmSecondsLeft} seconds remaining`
  } else if (uiState === 'restarting') {
    label = 'Restarting…'
  } else {
    label = 'Restart JARVIS'
  }

  return (
    <div id="restart-wrapper">
      <button
        id="restart-btn"
        className={className}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        onClick={onClick}
        onKeyDown={onKeyDown}
      >
        {uiState === 'restarting' && <span className="restart-spinner" aria-hidden="true" />}
        <span className="restart-btn-label">{label}</span>
      </button>
    </div>
  )
}
