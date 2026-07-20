# Todo App — frontend

Password-gated Next.js todo UI, backed directly by a Google Sheet (no
separate backend). Own standalone Vercel deployment, independent of the
`../../web` host. See [../README.md](../README.md) for how this fits with
the MCP server and Telegram bot, and [../ARCHITECTURE.md](../ARCHITECTURE.md)
for the sheet schema.

## Auth

Single shared passcode, session-cookie based — same pattern as `../../web`
(ported in independently rather than shared as a package, so each app's
passcode/session can be deployed and rotated on its own):

- `POST /api/session` checks the passcode (`SITE_PASSCODE`) and, on success,
  sets an HTTP-only, signed (`SESSION_SECRET`), 7-day sliding-expiry cookie.
- `middleware.ts` protects everything except `/login` and `/api/session`.
  Unauthenticated page requests redirect to `/login?returnTo=<path>`;
  unauthenticated `/api/*` requests get a `401 JSON` instead.
- `POST /api/session` is rate-limited to 5 attempts/minute per IP
  (in-memory, single-instance — see `lib/rate-limit.ts`) to blunt passcode
  brute-forcing.

## Required environment variables

Create `.env.local` (never commit it):

```
# Auth
SITE_PASSCODE=choose-a-strong-passcode
SESSION_SECRET=a-long-random-string-used-to-sign-the-session-cookie

# Google Sheets access (same service account used by ../mcp-server)
GOOGLE_SERVICE_ACCOUNT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
GOOGLE_SHEETS_SHEET_NAME=Todos

# Optional — override the sheet URL the UI reads from.
NEXT_PUBLIC_TODO_SOURCE=
```

Generate `SESSION_SECRET` with:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Neither `SITE_PASSCODE` nor `SESSION_SECRET` are ever sent to the client —
only the signed session cookie is.

## Running locally

```bash
npm install
npm run dev
```

Open http://localhost:3000, enter the passcode from `SITE_PASSCODE`.

## Deploying

Own Vercel project (separate from `web`'s). Set the env vars above in the
Vercel project settings (Production + Preview), then `vercel --prod` or
push to the linked git branch.
