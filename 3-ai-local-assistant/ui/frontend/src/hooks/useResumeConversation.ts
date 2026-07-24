import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

export type ResumeUiState = 'idle' | 'confirm-interrupt' | 'resuming'

const CONFIRM_WINDOW_SECONDS = 4
const RESUME_ARTIFICIAL_DELAY_MS = 500
const SUCCESS_MESSAGE_MS = 1500

const INTERRUPTIBLE_STATES = ['listening', 'thinking', 'speaking']

/**
 * Drives the "Resume this Conversation" button. Mirrors useNewConversation's
 * confirm-interrupt state machine shape.
 *
 * Note on the actual resume call: the backend has no standalone "resume"
 * endpoint — POST /chat only resumes a conversation (reconstructs
 * brain.history) as a side effect of sending a real user message, and it
 * rejects empty messages. So this hook can't fire a real resume request at
 * click time without injecting a fake user turn into the transcript.
 * Instead, "resuming" here means: confirm JARVIS is reachable (reusing the
 * already-tracked SSE `connected` state — no extra network round trip),
 * then hand off to the caller to make this conversation the resumed one
 * client-side (swap the live transcript baseline, remember the
 * conversation_id so it's attached to the *next* /chat call). The actual
 * server-side resume happens transparently on that next chat message.
 */
export function useResumeConversation(
  currentState: string,
  connected: boolean,
  onCommit: () => void,
  isBusy: boolean
) {
  const [uiState, setUiState] = useState<ResumeUiState>('idle')
  const [confirmSecondsLeft, setConfirmSecondsLeft] = useState(0)
  const [statusOverride, setStatusOverride] = useState<string | null>(null)

  const confirmRevertTimer = useRef<number | null>(null)
  const confirmTickTimer = useRef<number | null>(null)
  const resumeDelayTimer = useRef<number | null>(null)
  const successMessageTimer = useRef<number | null>(null)

  const connectedRef = useRef(connected)
  connectedRef.current = connected

  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

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

  const clearResumeDelayTimer = () => {
    if (resumeDelayTimer.current) {
      clearTimeout(resumeDelayTimer.current)
      resumeDelayTimer.current = null
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
      clearResumeDelayTimer()
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
      'Resuming will interrupt JARVIS. Click again within 4 seconds, or press Escape to cancel.'
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

  const commit = () => {
    clearConfirmTimers()
    setUiState('resuming')
    setStatusOverride(null)

    clearResumeDelayTimer()
    resumeDelayTimer.current = window.setTimeout(() => {
      if (!connectedRef.current) {
        setStatusOverride("Couldn't resume conversation — JARVIS may be unreachable.")
        setUiState('idle')
        return
      }

      onCommitRef.current()
      setStatusOverride('Resumed conversation.')
      setUiState('idle')
      clearSuccessMessageTimer()
      successMessageTimer.current = window.setTimeout(() => {
        setStatusOverride(null)
      }, SUCCESS_MESSAGE_MS)
    }, RESUME_ARTIFICIAL_DELAY_MS)
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
    // No-op while "resuming" — button is disabled anyway.
  }

  const handleKeyDown = (evt: KeyboardEvent<HTMLButtonElement>) => {
    if (evt.key === 'Escape' && uiState === 'confirm-interrupt') {
      evt.preventDefault()
      clearConfirmTimers()
      resetButton()
      setStatusOverride(null)
    }
  }

  const reset = () => {
    clearConfirmTimers()
    clearResumeDelayTimer()
    clearSuccessMessageTimer()
    setUiState('idle')
    setStatusOverride(null)
  }

  return { uiState, confirmSecondsLeft, statusOverride, handleClick, handleKeyDown, reset }
}
