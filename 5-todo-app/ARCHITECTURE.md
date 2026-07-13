# Todo system architecture

## Source of truth

Google Sheet is the single source of truth. No local DB, no sync layer.

- Sheet ID: `1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U`
- Tab: `Todos`
- Schema (header row): `id | description | status | source | created | done_date`
- `status`: `idea` | `in_progress` | `done`
- `source`: `manual`, `reel:<link>`, `telegram`, or other free-form tag (traceability)
- Service account: `local-sa-todo-app@genai-406713.iam.gserviceaccount.com`, key at
  `C:\Users\Cristhian\Documents\projects\genai-406713-98a02f72ea99.json`, shared as
  **Editor** on the sheet.

## Components

1. **`mcp-server/`** — local MCP server (stdio), used from Claude Code/Desktop.
   Reads/writes the sheet directly via Sheets REST API + `google-auth-library`
   JWT auth. Tools: `add_task`, `list_open_tasks`, `mark_task_done`,
   `edit_task`, `delete_task`, `git_status_summary`.

2. **`frontend/`** — Next.js todo app (deployed to Vercel). Reads/writes the
   same sheet/schema directly. No backend of its own, no sync step with the
   MCP server — both clients hit the same sheet.

3. **Telegram → Sheet automation** (Make.com scenario, active) — see
   `TELEGRAM-SETUP.md`. Forwards Telegram messages into the sheet tagged
   `source: telegram`, as a third capture path alongside the frontend and
   the MCP `add_task` tool.

4. **Reel → todo flow** (manual, in Claude Code sessions) — user sends a
   reel link + instructions directly to Claude in a session; Claude adds a
   row via `add_task` (source tagged `reel:<link>`). Local transcription
   (yt-dlp + whisper) is a separate concern, not wired into this flow.

## Why this shape

- Single source of truth (Sheet) removes the need for pull/push sync logic
  between local, mobile, and Telegram.
- MCP server talks Sheets API directly instead of maintaining its own store —
  same reason: avoid a second copy of state to keep consistent.
- Telegram capture goes through Make rather than a self-hosted bot process —
  no bot infra to run/maintain locally; Make owns the webhook and the bot
  token.
