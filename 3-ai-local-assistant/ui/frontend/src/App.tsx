import { useEffect, useRef, useState } from 'react'
import ConnectionBanner from './components/ConnectionBanner'
import VoiceOrb, { type VoiceOrbProps } from './components/VoiceOrb'
import StatusText from './components/StatusText'
import RestartButton from './components/RestartButton'
import NewConversationButton from './components/NewConversationButton'
import HistoryButton from './components/HistoryButton'
import TranscriptPanel from './components/TranscriptPanel'
import HistoryListPanel from './components/HistoryListPanel'
import HistoricalTranscriptPanel from './components/HistoricalTranscriptPanel'
import ChatInput from './components/ChatInput'
import { useJarvisState } from './hooks/useJarvisState'
import { useTranscript, type TranscriptEntry } from './hooks/useTranscript'
import { useRestart } from './hooks/useRestart'
import { useNewConversation } from './hooks/useNewConversation'
import { useConversations, type ConversationSummary } from './hooks/useConversations'
import { useConversationView } from './hooks/useConversationView'
import { useResumeConversation } from './hooks/useResumeConversation'

const STATES = [
  'off',
  'wake_listening',
  'listening',
  'thinking',
  'speaking',
  'error',
  'restarting',
]

type PanelMode = 'live' | 'list' | 'historical'

function App() {
  const { state, detail, amplitude, connected, applyState } = useJarvisState()
  const [transcriptPaused, setTranscriptPaused] = useState(false)
  const { entries, clear, restore } = useTranscript(transcriptPaused)

  const [panelMode, setPanelMode] = useState<PanelMode>('live')
  const [selectedConversation, setSelectedConversation] = useState<ConversationSummary | null>(null)
  // The active/live conversation_id, once known (set on a successful resume;
  // cleared on New Conversation). Used to tag the "current" row in the
  // history list and to skip re-fetching when the user clicks that row.
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  // Set on resume click (before confirmation); consumed by useChat on the
  // *first* sendMessage call after a resume. Only cleared once that call
  // actually succeeds — see handleResumeSuccess — so a failed attempt
  // naturally retries with the same conversation_id on the next send.
  const [pendingResumeId, setPendingResumeId] = useState<string | null>(null)

  const liveSnapshotRef = useRef<TranscriptEntry[]>([])

  const conversationsHook = useConversations()
  const conversationView = useConversationView()

  // The two mutating actions (restart / new conversation) each need to know
  // whether the *other* one is busy so they can never both fire at once.
  // Their uiState values are mutually dependent within a single render, so
  // track "is the other one busy" one render behind via effects rather than
  // reading each other's uiState directly in the same pass.
  const [newConvBusy, setNewConvBusy] = useState(false)
  const [resumeBusy, setResumeBusy] = useState(false)

  const {
    uiState: restartUiState,
    confirmSecondsLeft: restartConfirmSecondsLeft,
    statusOverride: restartOverride,
    handleClick: handleRestartClick,
    handleKeyDown: handleRestartKeyDown,
  } = useRestart(state, applyState, newConvBusy || resumeBusy)

  const {
    uiState: newConvUiState,
    confirmSecondsLeft: newConvConfirmSecondsLeft,
    statusOverride: newConvOverride,
    handleClick: handleNewConvClick,
    handleKeyDown: handleNewConvKeyDown,
  } = useNewConversation(state, entries, clear, restore, restartUiState !== 'idle' || resumeBusy)

  const commitResume = () => {
    if (!selectedConversation) return
    restore(conversationView.entries, { liftCutoff: true })
    // Do NOT set activeConversationId here — it's only committed once the
    // follow-up /chat call that actually attaches conversation_id succeeds
    // (see handleResumeSuccess). Until then this conversation is only
    // "pending" resume, not confirmed active, so the user can still
    // re-select it from history and retry if the next message fails.
    setPendingResumeId(selectedConversation.conversation_id)
    // Keep the poller paused here: the backend hasn't actually resumed
    // conversation_id yet (that only happens as a side effect of the next
    // /chat call), so GET /transcript would still return the old live
    // conversation's entries and clobber this optimistic restore. Only
    // unpause once handleResumeSuccess confirms the backend has switched.
    setPanelMode('live')
    setSelectedConversation(null)
  }

  // Called by ChatInput/useChat once the /chat request carrying
  // conversation_id actually succeeded — this is the only point at which a
  // resume is considered confirmed. Only now is it safe to let the poller
  // resume, since the backend's brain.conversation_id has genuinely switched.
  const handleResumeSuccess = (conversationId: string) => {
    setActiveConversationId(conversationId)
    // Do NOT set transcriptPaused here directly - this callback fires
    // asynchronously and may resolve after the user has already navigated
    // elsewhere (e.g. to a different historical conversation). Clearing
    // pendingResumeId lets the derived-state effect above recompute
    // transcriptPaused from whatever panelMode/pendingResumeId actually are
    // at the time this resolves, instead of blindly forcing it false.
    setPendingResumeId(null)
  }

  const {
    uiState: resumeUiState,
    confirmSecondsLeft: resumeConfirmSecondsLeft,
    statusOverride: resumeOverride,
    handleClick: handleResumeClick,
    handleKeyDown: handleResumeKeyDown,
    reset: resetResume,
  } = useResumeConversation(state, connected, commitResume, restartUiState !== 'idle' || newConvBusy)

  const restartDisabled =
    !connected ||
    restartUiState === 'restarting' ||
    newConvUiState !== 'idle' ||
    resumeBusy ||
    panelMode === 'historical'
  const newConvDisabled =
    !connected ||
    newConvUiState === 'clearing' ||
    restartUiState !== 'idle' ||
    resumeBusy ||
    panelMode === 'historical'
  const historyDisabled = restartUiState !== 'idle' || newConvUiState !== 'idle' || resumeBusy

  useEffect(() => {
    setNewConvBusy(newConvUiState !== 'idle')
  }, [newConvUiState])

  useEffect(() => {
    setResumeBusy(resumeUiState !== 'idle')
  }, [resumeUiState])

  // Pause transcript polling during the optimistic clear/rollback window, and
  // while viewing a historical (paused/snapshotted) conversation, so the
  // poller can't visually overwrite either with stale/live server data.
  useEffect(() => {
    setTranscriptPaused(
      newConvUiState === 'clearing' || panelMode === 'historical' || pendingResumeId !== null
    )
  }, [newConvUiState, panelMode, pendingResumeId])

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

  const openHistory = () => {
    setPanelMode('list')
    conversationsHook.refetch()
  }

  const closeHistoryToLive = () => {
    setPanelMode('live')
    setSelectedConversation(null)
    conversationView.reset()
  }

  const handleHistoryButtonClick = () => {
    if (panelMode === 'list') {
      closeHistoryToLive()
    } else {
      openHistory()
    }
  }

  const handleSelectConversation = (conv: ConversationSummary) => {
    if (conv.conversation_id === activeConversationId) {
      // Already the live conversation — just go back to the live view.
      closeHistoryToLive()
      return
    }
    liveSnapshotRef.current = entries
    setSelectedConversation(conv)
    setPanelMode('historical')
    setTranscriptPaused(true)
    resetResume()
    conversationView.load(conv.conversation_id)
  }

  const handleBackToLive = () => {
    restore(liveSnapshotRef.current)
    // Abandon any resume that was committed but never confirmed (see
    // commitResume/handleResumeSuccess) — backing out of the history view
    // should not leave a stale pending resume around to block the poller
    // or get silently attached to a later /chat call.
    setPendingResumeId(null)
    setTranscriptPaused(false)
    setPanelMode('live')
    setSelectedConversation(null)
    resetResume()
    conversationView.reset()
  }

  const handleNewConversationClick = () => {
    setActiveConversationId(null)
    setPendingResumeId(null)
    handleNewConvClick()
  }

  return (
    <div className="control-column">
      <ConnectionBanner connected={connected} />

      <VoiceOrb state={state as VoiceOrbProps['state']} amplitude={amplitude} />

      <StatusText
        state={state}
        detail={detail}
        override={restartOverride ?? newConvOverride ?? resumeOverride}
      />

      <NewConversationButton
        uiState={newConvUiState}
        confirmSecondsLeft={newConvConfirmSecondsLeft}
        onClick={handleNewConversationClick}
        onKeyDown={handleNewConvKeyDown}
        disabled={newConvDisabled}
      />

      <HistoryButton open={panelMode === 'list'} onClick={handleHistoryButtonClick} disabled={historyDisabled} />

      <RestartButton
        uiState={restartUiState}
        confirmSecondsLeft={restartConfirmSecondsLeft}
        onClick={handleRestartClick}
        onKeyDown={handleRestartKeyDown}
        disabled={restartDisabled}
      />

      {panelMode === 'live' && <TranscriptPanel entries={entries} />}

      {panelMode === 'list' && (
        <HistoryListPanel
          status={conversationsHook.status}
          conversations={conversationsHook.conversations}
          activeConversationId={activeConversationId}
          onSelect={handleSelectConversation}
          onRetry={conversationsHook.refetch}
        />
      )}

      {panelMode === 'historical' && selectedConversation && (
        <HistoricalTranscriptPanel
          status={conversationView.status}
          entries={conversationView.entries}
          conversationId={selectedConversation.conversation_id}
          firstTs={selectedConversation.first_ts}
          onBack={handleBackToLive}
          onRetry={() => conversationView.load(selectedConversation.conversation_id)}
          resumeUiState={resumeUiState}
          resumeConfirmSecondsLeft={resumeConfirmSecondsLeft}
          onResumeClick={handleResumeClick}
          onResumeKeyDown={handleResumeKeyDown}
          resumeDisabled={!connected || restartUiState !== 'idle' || newConvBusy}
        />
      )}

      <ChatInput
        viewingHistory={panelMode === 'historical'}
        pendingResumeId={pendingResumeId}
        onResumeSuccess={handleResumeSuccess}
      />
    </div>
  )
}

export default App
