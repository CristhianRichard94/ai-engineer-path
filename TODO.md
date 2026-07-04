# AI Engineer Journey — TODO / Ideas

## 4. MCP server (new project)
Build own MCP server exposing tools/resources over existing stack.
- [ ] Pick host: local stdio server first (simplest), skip HTTP/SSE transport til needed
- [ ] Tools: wrap doc-bot's RAG query as a tool (`search_docs(query)`), expose local-assistant's spotify/audio controls as tools
- [ ] Resources: expose doc-bot's ingested docs as MCP resources (read-only, URI per doc)
- [ ] Prompts: canned prompt templates for common doc-bot queries
- [ ] Test with Claude Desktop / Claude Code as client (`claude mcp add`)
- [ ] Add auth if exposed beyond localhost — stdio has none needed

## Other ideas
- [ ] Add streaming responses to ai-chat backend (SSE) — check if FastAPI/Flask already supports before adding lib
- [ ] Add eval harness for doc-bot RAG (retrieval precision/recall on a fixed Q&A set)
- [ ] Add conversation memory/history persistence to ai-chat (currently stateless?)
- [ ] Local-assistant: add a "skills" plugin pattern only if adding 3rd+ skill, not before (YAGNI)
- [ ] Try swapping doc-bot vector store for pgvector/sqlite-vec instead of current one — compare cost/simplicity
- [ ] Add basic observability: log latency + token usage per request across all 3 apps
- [ ] Dockerize each subproject for consistent local runs (skip if Fly.io deploy already covers this)
