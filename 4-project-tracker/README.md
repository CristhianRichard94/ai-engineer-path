# 4-project-tracker — Todo System

Google-Sheet-backed todo system with three ways in: a web UI, a local MCP
server for Claude Code/Desktop, and a Telegram bot. No local DB — the Sheet
is the single source of truth for all three. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the full data-flow rationale.

## Layout

```
4-project-tracker/
├── frontend/            Next.js todo UI, own standalone Vercel deployment,
│                         password-gated (see below)
├── mcp-server/           Local MCP stdio server for Claude Code/Desktop
├── ARCHITECTURE.md        Sheet schema, source-of-truth rationale
└── TELEGRAM-SETUP.md     Make.com scenario + Telegram bot setup
```

## Where it's deployed

`frontend/` is its own standalone Next.js app, deployed to its own Vercel
project — separate from `../web` (which hosts apps 1 and 2). It ships with
the same shared-passcode session-cookie auth pattern as `../web`
(`lib/session.ts`, `lib/rate-limit.ts`, `middleware.ts`, `/login`,
`/api/session`), ported in rather than shared, so a compromise of one app's
passcode doesn't affect the other and each can be deployed/rotated
independently. `POST /api/session` is rate-limited (5 attempts/min/IP) to
blunt passcode brute-forcing.

## Components

### 1. `frontend/` — Next.js UI (password-protected)
Talks to `app/api/todos/route.ts`, which calls Google Sheets directly via
a service-account JWT (`app/services/sheets-service.ts`). No backend
process of its own. `/`, `/api/todos` sit behind the passcode cookie;
`/login` and `/api/session` are the only unauthenticated routes.

```bash
cd frontend && npm install && npm run dev
```

Requires `SITE_PASSCODE`, `SESSION_SECRET` (auth) and
`GOOGLE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY`,
`GOOGLE_SHEETS_SHEET_NAME` (Sheets access) as env vars — see
`frontend/.env.local.example` if present, or the vars documented inline in
`lib/session.ts` / `app/services/sheets-service.ts`.

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

- **Web**: open the standalone deployed app, enter the passcode.
- **Claude Code**: `add_task` via the `project-tracker` MCP server.
- **Telegram**: message the bot directly.

All three write to the same sheet — no sync step needed between them.
