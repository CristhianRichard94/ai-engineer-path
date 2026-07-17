# JARVIS Control UI (React + TypeScript + Vite)

React port of the JARVIS control UI: the orb status indicator, status text,
two-step Restart button, and terminal-styled transcript panel. Talks to the
Flask backend in `ui/server.py` via `/state` (SSE), `/transcript` (polled
JSON), and `/restart` (POST).

## Dev mode

Runs the Flask backend and the Vite dev server side by side. The dev server
proxies `/state`, `/transcript`, and `/restart` to `http://127.0.0.1:5151`
(see `vite.config.ts`), so start the backend first:

```bash
# terminal 1, from the repo root
python ui/server.py

# terminal 2, from ui/frontend/
npm install
npm run dev
```

Open the URL Vite prints (typically http://localhost:5173/).

## Production build

```bash
cd ui/frontend
npm install
npm run build
```

This outputs static assets to `ui/frontend/dist/`. `ui/server.py` serves
that directory directly at `/`, so once built you only need to run:

```bash
python ui/server.py
```

and open http://127.0.0.1:5151/ (or whatever `JARVIS_UI_PORT` is set to).
