# web — Recruiter-safe host app

Single Next.js (App Router) app that hosts both `1-ai-chat` and
`2-context-aware-doc-bot` frontends behind a shared passcode gate, so the
whole site can be put behind a public URL without exposing the
OpenAI-key-backed backends to unauthenticated traffic/bots.

## Routes

- `/login` — passcode entry (unauthenticated).
- `/` — hub listing the two apps (authenticated).
- `/chat` — the AI Chat UI (ported from `1-ai-chat/frontend`), proxied to the
  chat backend via `/api/chat/*`.
- `/docbot` — the Context-Aware Doc Bot UI (ported from
  `2-context-aware-doc-bot/frontend`), proxied to the doc-bot backend via
  `/api/docbot/*`.

The two FastAPI backends (`1-ai-chat/backend`, `2-context-aware-doc-bot/backend`)
are unchanged — run them separately. This app only proxies to them.

## Auth model

- A single shared passcode (`SITE_PASSCODE`), compared server-side only
  (never sent to the client) in `POST /api/session`.
- On success, an HTTP-only, `SameSite=Lax` cookie signed with
  `SESSION_SECRET` is set (7-day sliding expiry — renewed on every
  authenticated request by `middleware.ts`). `Secure` is enforced in
  production only, so local `http://localhost` dev keeps working.
- `middleware.ts` protects `/`, `/chat`, `/docbot`, and the `/api/chat/*` /
  `/api/docbot/*` proxy routes. Unauthenticated page requests redirect to
  `/login?returnTo=<path>`; unauthenticated proxy requests return `401 JSON`
  so the page can show a dismissible "session expired" banner instead of a
  jarring redirect.
- `POST /api/session` is rate-limited to 5 attempts/minute per IP
  (in-memory, single-instance — see comment in `lib/rate-limit.ts`).

## Required environment variables

Create `web/.env.local` (never commit it):

```
SITE_PASSCODE=choose-a-strong-passcode
SESSION_SECRET=a-long-random-string-used-to-sign-the-session-cookie

# Optional — override if the backends run somewhere other than localhost.
CHAT_BACKEND_URL=http://127.0.0.1:8000
DOCBOT_BACKEND_URL=http://127.0.0.1:5000

# Optional — same GitHub token support as the original doc-bot frontend.
# SECURITY WARNING: this is a NEXT_PUBLIC_ var and ends up in the client JS
# bundle. Use a fine-grained, read-only, public-repo-only token if set.
NEXT_PUBLIC_GITHUB_TOKEN=
```

`SESSION_SECRET` should be a long random value, e.g. generate one with:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Neither `SITE_PASSCODE` nor `SESSION_SECRET` are ever sent to the client —
only the signed session cookie is.

## Running locally

```bash
# Terminal 1 — chat backend
cd ../1-ai-chat/backend && uvicorn main:app --reload --port 8000

# Terminal 2 — doc-bot backend
cd ../2-context-aware-doc-bot/backend && python main.py  # see that app's README

# Terminal 3 — this app
npm install
npm run dev
```

Then open http://localhost:3000, enter the passcode from `SITE_PASSCODE`,
and use the hub to reach either app.
