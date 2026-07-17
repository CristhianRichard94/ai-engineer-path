import { useEffect } from 'react'
import ConnectionBanner from './components/ConnectionBanner'
import VoiceOrb, { type VoiceOrbProps } from './components/VoiceOrb'
import StatusText from './components/StatusText'
import RestartButton from './components/RestartButton'
import TranscriptPanel from './components/TranscriptPanel'
import { useJarvisState } from './hooks/useJarvisState'
import { useTranscript } from './hooks/useTranscript'
import { useRestart } from './hooks/useRestart'

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
  const transcript = useTranscript()
  const { uiState, confirmSecondsLeft, statusOverride, handleClick, handleKeyDown } = useRestart(
    state,
    applyState
  )

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

      <StatusText state={state} detail={detail} override={statusOverride} />

      <RestartButton
        uiState={uiState}
        confirmSecondsLeft={confirmSecondsLeft}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      />

      <TranscriptPanel entries={transcript} />
    </div>
  )
}

export default App
