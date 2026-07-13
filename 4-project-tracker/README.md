# 4-project-tracker — Todo System

Google-Sheet-backed todo system with three ways in: a web UI, a local MCP
server for Claude Code/Desktop, and a Telegram bot. No local DB — the Sheet
is the single source of truth for all three. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the full data-flow rationale.

## Layout

```
4-project-tracker/
├── frontend/            Next.js todo UI (source of truth for the /todo route
│                         hosted in ../web — see below)
├── mcp-server/           Local MCP stdio server for Claude Code/Desktop
├── ARCHITECTURE.md        Sheet schema, source-of-truth rationale
└── TELEGRAM-SETUP.md     Make.com scenario + Telegram bot setup
```

## Where it's actually deployed

`frontend/` is the original standalone Next.js app and stays here as the
source of truth for that UI, but the **live deployment is `../web`'s
`/todo` route** — the same passcode-gated host that serves apps 1 and 2
(`../web/app/todo`, `../web/app/api/todos`). This keeps the todo sheet
behind the same auth as everything else instead of shipping a second,
unauthenticated public URL. If you change UI behavior, mirror the change
in both `frontend/app` and `web/app/todo` (or promote one to be a shared
package if the duplication gets painful — not worth it yet at this size).

## Components

### 1. `frontend/` — Next.js UI
Talks to `app/api/todos/route.ts`, which calls Google Sheets directly via
a service-account JWT (`app/services/sheets-service.ts`). No backend
process of its own.

```bash
cd frontend && npm install && npm run dev
```

Requires `GOOGLE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY`,
`GOOGLE_SHEETS_SHEET_NAME` (see `../web/README.md`'s env var table for the
values — same account is reused).

### 2. `mcp-server/` — Claude Code / Claude Desktop tool
Stdio MCP server exposing `list_open_tasks`, `add_task`, `mark_task_done`,
`edit_task`, `delete_task`, `git_status_summary`. See
[mcp-server/README.md](mcp-server/README.md) for env vars and registration.
Registered in this repo's `.mcp.json` and, for use outside this repo, in
`~/.claude.json` under `mcpServers.project-tracker`.

### 3. Telegram bot (Make.com scenario)
Forwards Telegram messages into the sheet, tagged `source: telegram`.
No bot process to run locally — Make owns the webhook and the bot token.
See [TELEGRAM-SETUP.md](TELEGRAM-SETUP.md).

## Sheet schema

Tab `Todos`, header row: `id | description | status | source | created | done_date`.
`status`: `idea` | `in_progress` | `done`. `source`: `manual`, `telegram`,
`reel:<link>`, or other free-form tag. Sheet ID and service account details
are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Adding a task, three ways

- **Web**: open `/todo` on the hosted site.
- **Claude Code**: `add_task` via the `project-tracker` MCP server.
- **Telegram**: message the bot directly.

All three write to the same sheet — no sync step needed between them.
