export default function HistoryButton({
  open,
  onClick,
  disabled = false,
}: {
  open: boolean
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      id="history-btn"
      className="history-btn"
      type="button"
      disabled={disabled}
      aria-expanded={open}
      aria-controls="history-panel"
      onClick={onClick}
    >
      {open ? 'History ▲' : 'History'}
    </button>
  )
}
