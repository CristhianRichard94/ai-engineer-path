import { useEffect, useState } from 'react'
import ConnectionBanner from './components/ConnectionBanner'
import VoiceOrb, { type VoiceOrbProps } from './components/VoiceOrb'
import StatusText from './components/StatusText'
import RestartButton from './components/RestartButton'
import NewConversationButton from './components/NewConversationButton'
import TranscriptPanel from './components/TranscriptPanel'
import ChatInput from './components/ChatInput'
import { useJarvisState } from './hooks/useJarvisState'
import { useTranscript } from './hooks/useTranscript'
import { useRestart } from './hooks/useRestart'
import { useNewConversation } from './hooks/useNewConversation'

const STATES = [
  'off',
  'wake_listening',
  'listening',
  'thinking',
  'speaking',
  'error',
  'restarting',
]

function App() {
  const { state, detail, amplitude, connected, applyState } = useJarvisState()
  const [transcriptPaused, setTranscriptPaused] = useState(false)
  const { entries, clear, restore } = useTranscript(transcriptPaused)

  // The two mutating actions (restart / new conversation) each need to know
  // whether the *other* one is busy so they can never both fire at once.
  // Their uiState values are mutually dependent within a single render, so
  // track "is the other one busy" one render behind via effects rather than
  // reading each other's uiState directly in the same pass.
  const [newConvBusy, setNewConvBusy] = useState(false)

  const {
    uiState: restartUiState,
    confirmSecondsLeft: restartConfirmSecondsLeft,
    statusOverride: restartOverride,
    handleClick: handleRestartClick,
    handleKeyDown: handleRestartKeyDown,
  } = useRestart(state, applyState, newConvBusy)

  const {
    uiState: newConvUiState,
    confirmSecondsLeft: newConvConfirmSecondsLeft,
    statusOverride: newConvOverride,
    handleClick: handleNewConvClick,
    handleKeyDown: handleNewConvKeyDown,
  } = useNewConversation(state, entries, clear, restore, restartUiState !== 'idle')

  const restartDisabled = !connected || restartUiState === 'restarting' || newConvUiState !== 'idle'
  const newConvDisabled = !connected || newConvUiState === 'clearing' || restartUiState !== 'idle'

  useEffect(() => {
    setNewConvBusy(newConvUiState !== 'idle')
  }, [newConvUiState])

  // Pause transcript polling during the optimistic clear/rollback window so
  // the poll can't visually "undo" the clear with stale server data.
  useEffect(() => {
    setTranscriptPaused(newConvUiState === 'clearing')
  }, [newConvUiState])

  // Toggle body.state-* classes, same as the original app.js, so
  // animation.css selectors (which target `body.state-*`) keep working.
  useEffect(() => {
    const body = document.body
    STATES.forEach((s) => body.classList.remove('state-' + s))
    body.classList.add('state-' + state)
    return () => {
      body.classList.remove('state-' + state)
    }
  }, [state])

  return (
    <div className="control-column">
      <ConnectionBanner connected={connected} />

      <VoiceOrb state={state as VoiceOrbProps['state']} amplitude={amplitude} />

      <StatusText state={state} detail={detail} override={restartOverride ?? newConvOverride} />

      <NewConversationButton
        uiState={newConvUiState}
        confirmSecondsLeft={newConvConfirmSecondsLeft}
        onClick={handleNewConvClick}
        onKeyDown={handleNewConvKeyDown}
        disabled={newConvDisabled}
      />

      <RestartButton
        uiState={restartUiState}
        confirmSecondsLeft={restartConfirmSecondsLeft}
        onClick={handleRestartClick}
        onKeyDown={handleRestartKeyDown}
        disabled={restartDisabled}
      />

      <TranscriptPanel entries={entries} />

      <ChatInput />
    </div>
  )
}

export default App
