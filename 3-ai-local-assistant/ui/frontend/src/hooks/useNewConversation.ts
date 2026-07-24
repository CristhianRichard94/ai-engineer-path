import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { TranscriptEntry } from './useTranscript'

export type NewConversationUiState = 'idle' | 'confirm-interrupt' | 'clearing'

const CONFIRM_WINDOW_SECONDS = 4
const NEW_CONVERSATION_TIMEOUT_MS = 5000
const SUCCESS_MESSAGE_MS = 1500

const INTERRUPTIBLE_STATES = ['listening', 'thinking', 'speaking']

/**
 * Drives the "New Conversation" button: for interruptible JARVIS states
 * (listening/thinking/speaking) requires a confirm click within a 4s
 * window before committing; for any other state (off/wake_listening/error)
 * commits immediately. Clears the transcript optimistically and reverts on
 * failure. Mirrors useRestart.ts's state-machine shape.
 */
export function useNewConversation(
  currentState: string,
  entries: TranscriptEntry[],
  onClear: () => void,
  onRestore: (snapshot: TranscriptEntry[]) => void,
  isBusy: boolean
) {
  const [uiState, setUiState] = useState<NewConversationUiState>('idle')
  const [confirmSecondsLeft, setConfirmSecondsLeft] = useState(0)
  const [statusOverride, setStatusOverride] = useState<string | null>(null)

  const confirmRevertTimer = useRef<number | null>(null)
  const confirmTickTimer = useRef<number | null>(null)
  const clearTimeoutTimer = useRef<number | null>(null)
  const successMessageTimer = useRef<number | null>(null)

  const entriesRef = useRef(entries)
  entriesRef.current = entries

  const clearConfirmTimers = () => {
    if (confirmRevertTimer.current) {
      clearTimeout(confirmRevertTimer.current)
      confirmRevertTimer.current = null
    }
    if (confirmTickTimer.current) {
      clearInterval(confirmTickTimer.current)
      confirmTickTimer.current = null
    }
  }

  const clearGuardTimeout = () => {
    if (clearTimeoutTimer.current) {
      clearTimeout(clearTimeoutTimer.current)
      clearTimeoutTimer.current = null
    }
  }

  const clearSuccessMessageTimer = () => {
    if (successMessageTimer.current) {
      clearTimeout(successMessageTimer.current)
      successMessageTimer.current = null
    }
  }

  useEffect(() => {
    return () => {
      clearConfirmTimers()
      clearGuardTimeout()
      clearSuccessMessageTimer()
    }
  }, [])

  const resetButton = () => {
    setUiState('idle')
    clearConfirmTimers()
  }

  const enterConfirmMode = () => {
    setUiState('confirm-interrupt')
    clearConfirmTimers()
    setConfirmSecondsLeft(CONFIRM_WINDOW_SECONDS)
    setStatusOverride(
      'Clearing the conversation will interrupt JARVIS. Click again within 4 seconds, or press Escape to cancel.'
    )

    confirmTickTimer.current = window.setInterval(() => {
      setConfirmSecondsLeft((s) => {
        const next = s - 1
        if (next <= 0) {
          clearConfirmTimers()
          resetButton()
          setStatusOverride(null)
          return 0
        }
        return next
      })
    }, 1000)

    confirmRevertTimer.current = window.setTimeout(() => {
      clearConfirmTimers()
      resetButton()
      setStatusOverride(null)
    }, CONFIRM_WINDOW_SECONDS * 1000)
  }

  const handleFailure = (snapshot: TranscriptEntry[]) => {
    onRestore(snapshot)
    setStatusOverride("Couldn't clear conversation — JARVIS may be unreachable.")
    setUiState('idle')
  }

  const commit = () => {
    clearConfirmTimers()
    setUiState('clearing')
    setStatusOverride(null)

    const snapshot = entriesRef.current
    onClear()

    let settled = false

    clearGuardTimeout()
    clearTimeoutTimer.current = window.setTimeout(() => {
      if (settled) return
      settled = true
      handleFailure(snapshot)
    }, NEW_CONVERSATION_TIMEOUT_MS)

    fetch('/new-conversation', { method: 'POST' })
      .then((res) => {
        if (settled) return
        settled = true
        clearGuardTimeout()
        if (!res.ok) {
          handleFailure(snapshot)
          return
        }
        setStatusOverride('Conversation cleared.')
        clearSuccessMessageTimer()
        successMessageTimer.current = window.setTimeout(() => {
          setStatusOverride(null)
        }, SUCCESS_MESSAGE_MS)
        setUiState('idle')
      })
      .catch(() => {
        if (settled) return
        settled = true
        clearGuardTimeout()
        handleFailure(snapshot)
      })
  }

  const handleClick = () => {
    if (isBusy) return

    if (uiState === 'idle') {
      if (INTERRUPTIBLE_STATES.includes(currentState)) {
        enterConfirmMode()
      } else {
        commit()
      }
    } else if (uiState === 'confirm-interrupt') {
      commit()
    }
    // No-op while "clearing" — button is disabled anyway.
  }

  const handleKeyDown = (evt: KeyboardEvent<HTMLButtonElement>) => {
    if (evt.key === 'Escape' && uiState === 'confirm-interrupt') {
      evt.preventDefault()
      clearConfirmTimers()
      resetButton()
      setStatusOverride(null)
    }
  }

  return { uiState, confirmSecondsLeft, statusOverride, handleClick, handleKeyDown }
}
