# Context-Aware Doc Bot

A full-stack RAG application. Paste a GitHub repo URL, wait for it to be indexed, then ask questions about the codebase in natural language.

## Pipeline

```
GitHub URL → fetch zip → chunk + embed → Qdrant
                                              ↓
User prompt → vector search → context injection → OpenAI LLM → answer
```

1. **Index** — Flask dispatches a Celery task that downloads the repo zip, splits files into chunks, embeds them via OpenAI, and stores vectors in Qdrant.
2. **Commit check** — before indexing, the latest GitHub commit hash is compared against what was stored last time. Re-indexing is skipped when the repo is already up to date.
3. **Query** — the user prompt is embedded, the top-k matching chunks are retrieved from Qdrant, injected as context, and sent to the LLM.

## Stack

| Layer | Technology |
|---|---|
| Backend API | Flask + Flask-CORS |
| Async workers | Celery + Redis |
| Vector DB | Qdrant |
| Embeddings + LLM | OpenAI (via langchain-openai / llama-index) |
| Frontend | Next.js (TypeScript) |
| Container orchestration | Docker Compose |

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/index` | Submit a repo URL for indexing. Returns `job_id` or `already_indexed`. |
| `GET` | `/api/index/<job_id>` | Poll indexing task status (`pending` / `success` / `failure`). |
| `POST` | `/api/prompt` | Query the indexed repo. Body: `{ url, prompt }`. Returns `{ response }`. |
| `GET` | `/api/docs` | Swagger UI (interactive API documentation). |

### Example: index a repo

```bash
curl -X POST http://localhost:5000/api/index \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/owner/repo"}'
# → {"job_id": "abc123", "commit": "a1b2c3d"}

# poll until status == "success"
curl http://localhost:5000/api/index/abc123
# → {"job_id": "abc123", "status": "success"}
```

### Example: ask a question

```bash
curl -X POST http://localhost:5000/api/prompt \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/owner/repo", "prompt": "How is authentication handled?"}'
# → {"response": "Authentication is handled by ..."}
```

## Setup

**Prerequisites:** Docker Desktop, Node.js 18+

### 1. Configure environment

```bash
cp 2-context-aware-doc-bot/backend/.env.example 2-context-aware-doc-bot/backend/.env
```

### `.env` keys

```env
OPENAI_API_KEY=

QDRANT_API_KEY=
QDRANT_URL=http://qdrant:6333        # use http://localhost:6333 for local dev without Docker

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### 2. Start the full stack

```bash
cd 2-context-aware-doc-bot
docker compose up --build
```

This starts four services:

| Service | Port | Description |
|---|---|---|
| `api` | 5000 | Flask REST API |
| `worker` | — | Celery indexing worker |
| `redis` | 6379 | Celery broker + result backend |
| `qdrant` | 6333 | Vector database |

### 3. Start the frontend

```bash
cd 2-context-aware-doc-bot/frontend
npm install
npm run dev
# → http://localhost:3000
```

## Makefile shortcuts

```bash
make up        # docker compose up --build
make down      # docker compose down
make logs      # tail all service logs
make worker    # tail worker logs only
```

## Project structure

```
2-context-aware-doc-bot/
  backend/
    main.py           # Flask app + route definitions
    worker/
      app.py          # Celery app instance
      tasks.py        # index_repo_task, commit hash helpers
    model/
      vector_db.py    # Qdrant client: upsert, query, is_repo_indexed
    services/
      llm.py          # OpenAI LLM wrapper (llm_prompt)
    process/          # file chunking + embedding logic
    config.py         # env var loading
    logger.py         # structured logger
    openapi.yaml      # OpenAPI 3 spec (served at /api/docs)
    Dockerfile
  frontend/           # Next.js app
  docker-compose.yml
  Makefile
```
