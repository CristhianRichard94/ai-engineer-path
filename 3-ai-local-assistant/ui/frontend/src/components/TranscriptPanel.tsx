import { useEffect, useRef } from 'react'
import type { TranscriptEntry } from '../hooks/useTranscript'

function roleLabel(role: string) {
  return role === 'user' ? 'user@jarvis:~$' : 'jarvis>'
}

export default function TranscriptPanel({ entries }: { entries: TranscriptEntry[] }) {
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (entries.length > 0 && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [entries])

  return (
    <div id="transcript-panel" className="transcript-panel" aria-label="Conversation transcript">
      <div className="terminal-titlebar" aria-hidden="true">
        <span className="terminal-dot terminal-dot-red"></span>
        <span className="terminal-dot terminal-dot-amber"></span>
        <span className="terminal-dot terminal-dot-green"></span>
        <span className="terminal-title">jarvis@localhost:~</span>
      </div>
      <div id="transcript-log" className="transcript-log" role="log" aria-live="polite" ref={logRef}>
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
    </div>
  )
}
