/** Formats a unix-seconds timestamp as "Jul 20, 14:32". */
export function formatRowTime(ts: number): string {
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return ''
  const month = d.toLocaleString('en-US', { month: 'short' })
  const day = d.getDate()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${month} ${day}, ${hh}:${mm}`
}

/** Formats a unix-seconds timestamp as "2026-07-20" (used for fallback previews and titlebar labels). */
export function formatShortDate(ts: number): string {
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Short label derived from a conversation_id/first_ts, for the historical titlebar. */
export function shortConversationLabel(conversationId: string, firstTs?: number): string {
  if (typeof firstTs === 'number' && !Number.isNaN(firstTs)) {
    return formatShortDate(firstTs)
  }
  return conversationId.length > 8 ? conversationId.slice(0, 8) : conversationId
}

export function rowMetaTime(lastTs: number, turnCount: number): string {
  return `${formatRowTime(lastTs)} · ${turnCount} turn${turnCount === 1 ? '' : 's'}`
}
