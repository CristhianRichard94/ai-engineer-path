# AI Engineer Path

A collection of AI-powered applications built to explore and practice modern AI engineering concepts. This repository serves as a learning project demonstrating practical implementations of AI integrations, LLM interactions, and full-stack application development.

## 📚 Project Overview

This project is part of the **AI Engineer Path** learning initiative, showcasing various AI applications built with modern technologies. Each app demonstrates best practices for integrating AI services, building scalable backends, and creating responsive user interfaces.

---

## 🚀 Applications

| # | App | Description | README |
|---|---|---|---|
| 1 | **AI Chat** | Real-time chat interface backed by an OpenAI LLM. Streaming responses, conversation history, React + FastAPI. | [1-ai-chat/README.md](1-ai-chat/README.md) |
| 2 | **Context-Aware Doc Bot** | Paste a GitHub repo URL → async indexing (Celery + Qdrant) → ask questions about the codebase via RAG. Flask + Next.js. | [2-context-aware-doc-bot/README.md](2-context-aware-doc-bot/README.md) |
| 3 | **JARVIS — AI Local Voice Assistant** | Wake-word-activated voice assistant for Windows. Speech-to-text → GPT intent routing → TTS (Fish Speech / pyttsx3). | [3-ai-local-assistant/README.md](3-ai-local-assistant/README.md) |
| 4 | **Web (recruiter-safe host)** | Next.js app that hosts apps 1 and 2 behind a shared passcode gate for public deployment — the actual live entry point for this repo. | [web/README.md](web/README.md) |
| 5 | **Todo System** | Google-Sheet-backed todo system: Next.js frontend, MCP stdio server (`add_task`, `list_open_tasks`, `mark_task_done`, `edit_task`, `delete_task`, `git_status_summary`), and a Telegram→Sheet capture path via Make.com. | [5-todo-app/ARCHITECTURE.md](5-todo-app/ARCHITECTURE.md) |

---

## 🛠️ Getting Started

Each application has its own setup instructions documented in its respective README file.

### General Requirements
- Python 3.8+
- Node.js 18+
- Required API keys (see app-specific documentation)

Navigate to any application directory and follow the instructions in its README file for setup and deployment.

---

## 🔌 MCP Servers

This repo ships its own MCP server as part of [app 5](5-todo-app/mcp-server) — **project-tracker**, a stdio server exposing `list_open_tasks`, `add_task`, `mark_task_done`, `edit_task`, `delete_task`, and `git_status_summary` over the Todos Google Sheet (see [5-todo-app/ARCHITECTURE.md](5-todo-app/ARCHITECTURE.md)). Wired up via the project-scoped `.mcp.json`. Claude Code auto-detects it; approve the trust prompt on first use.

---

## 📋 Applications Overview

| App | Key AI tech | Backend | Frontend |
|---|---|---|---|
| AI Chat | OpenAI chat completions, streaming | FastAPI | React / Vite |
| Context-Aware Doc Bot | OpenAI embeddings, RAG, Qdrant | Flask + Celery | Next.js |
| JARVIS | Whisper STT, GPT-4o intent routing, Fish Speech TTS | Python (local) | — |

---

## 🔄 API Documentation

Each application provides its own API documentation. Backend services typically expose API documentation at:
- `/docs` - Interactive Swagger UI
- `/openapi.json` - OpenAPI specification

Refer to the application's README for specific endpoints and usage examples.

---

## 🎯 Project Growth

This repository is structured to accommodate multiple AI applications. Each new application:
- Gets its own numbered directory (2-, 3-, etc.)
- Includes a dedicated README with setup and documentation
- Demonstrates different AI engineering patterns and use cases
- Can use different tech stacks as appropriate

---

## 🔐 Security Considerations

- Keep API keys in `.env` files (never commit them)
- Use environment variables for sensitive data
- Validate all user inputs on both frontend and backend
- Implement rate limiting for production deployments
- Use HTTPS in production environments

---

## 📦 Common Technologies

This project typically uses:

**Frontend:**
- React-based frameworks (Next.js, Vite)
- TypeScript for type safety
- CSS frameworks (Tailwind CSS)
- ESLint for code quality

**Backend:**
- Python with FastAPI or similar frameworks
- Pydantic for data validation
- API client libraries for external services
- Environment variable management (python-dotenv)

Specific dependencies are documented in each application's README.

---

## 🚀 Deployment

Each application can be deployed independently. General guidelines:

**Frontend:**
- Build production bundles per app's documentation
- Deploy to platforms like Vercel, Netlify, or cloud providers
- Ensure environment variables are properly configured

**Backend:**
- Containerize with Docker if needed
- Deploy to cloud platforms (AWS, Heroku, Railway, etc.)
- Configure environment variables for production
- Set up appropriate logging and monitoring

See each application's README for specific deployment instructions.

---

## 📝 License

Built for educational purposes. No LICENSE file is present yet — treat as all-rights-reserved until one is added.

---

## 👨‍💻 Contributing

Contributions are welcome! Feel free to:
- Report issues
- Suggest new AI applications
- Improve existing implementations
- Add documentation

---

## 📧 Contact & Support

For questions or support regarding this AI Engineer Path project, feel free to reach out.

---

**Happy learning! 🚀 Let's build amazing AI applications together.**
