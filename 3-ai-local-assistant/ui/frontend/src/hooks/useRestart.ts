import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

export type RestartUiState = 'idle' | 'confirm' | 'restarting'

const CONFIRM_WINDOW_SECONDS = 4
const RESTART_TIMEOUT_MS = 15000

/**
 * Drives the two-step Restart button: arm -> confirm -> commit, with a
 * 4s confirm window, optimistic "restarting" state, and a 15s fallback
 * timeout if JARVIS never reports back "wake_listening" (success) or
 * "error" (failure). Mirrors app.js's restart flow.
 */
export function useRestart(
  currentState: string,
  applyState: (state: string, detail: string) => void
) {
  const [uiState, setUiState] = useState<RestartUiState>('idle')
  const [confirmSecondsLeft, setConfirmSecondsLeft] = useState(0)
  const [statusOverride, setStatusOverride] = useState<string | null>(null)

  const confirmRevertTimer = useRef<number | null>(null)
  const confirmTickTimer = useRef<number | null>(null)
  const restartTimeoutTimer = useRef<number | null>(null)
  const optimisticRestarting = useRef(false)

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

  const clearRestartTimeout = () => {
    if (restartTimeoutTimer.current) {
      clearTimeout(restartTimeoutTimer.current)
      restartTimeoutTimer.current = null
    }
  }

  const resetButton = () => {
    setUiState('idle')
    clearConfirmTimers()
    setStatusOverride(null)
  }

  // Resolve optimistic restart once JARVIS reports success or failure via SSE.
  useEffect(() => {
    if (!optimisticRestarting.current) return
    if (currentState === 'wake_listening' || currentState === 'error') {
      optimisticRestarting.current = false
      clearRestartTimeout()
      resetButton()
    }
  }, [currentState])

  useEffect(() => {
    return () => {
      clearConfirmTimers()
      clearRestartTimeout()
    }
  }, [])

  const enterConfirmMode = () => {
    setUiState('confirm')
    clearConfirmTimers()
    setConfirmSecondsLeft(CONFIRM_WINDOW_SECONDS)
    setStatusOverride(
      'Restart requires confirmation. Click again within 4 seconds, or press Escape to cancel.'
    )

    confirmTickTimer.current = window.setInterval(() => {
      setConfirmSecondsLeft((s) => {
        const next = s - 1
        if (next <= 0) {
          clearConfirmTimers()
          resetButton()
          return 0
        }
        return next
      })
    }, 1000)

    confirmRevertTimer.current = window.setTimeout(() => {
      clearConfirmTimers()
      resetButton()
    }, CONFIRM_WINDOW_SECONDS * 1000)
  }

  const commitRestart = () => {
    clearConfirmTimers()
    setUiState('restarting')
    setStatusOverride(null)

    optimisticRestarting.current = true
    applyState('restarting', '')

    fetch('/restart', { method: 'POST' }).catch(() => {
      // Network failure calling restart: let the 15s timeout handle it.
    })

    clearRestartTimeout()
    restartTimeoutTimer.current = window.setTimeout(() => {
      if (optimisticRestarting.current) {
        optimisticRestarting.current = false
        applyState('error', 'Restart failed — JARVIS did not come back online.')
        resetButton()
      }
    }, RESTART_TIMEOUT_MS)
  }

  const handleClick = () => {
    if (uiState === 'idle') {
      enterConfirmMode()
    } else if (uiState === 'confirm') {
      commitRestart()
    }
    // No-op while "restarting" — button is disabled anyway.
  }

  const handleKeyDown = (evt: KeyboardEvent<HTMLButtonElement>) => {
    if (evt.key === 'Escape' && uiState === 'confirm') {
      evt.preventDefault()
      clearConfirmTimers()
      resetButton()
    }
  }

  return { uiState, confirmSecondsLeft, statusOverride, handleClick, handleKeyDown }
}
