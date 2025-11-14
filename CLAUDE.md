# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **Open WebUI** (formerly Ollama WebUI), a fork customized as "impact-flow-mvp". It's a full-stack web application that provides a chat interface for interacting with LLMs (Ollama, OpenAI-compatible APIs). The project combines a **FastAPI Python backend** with a **SvelteKit TypeScript frontend**.

## Architecture

### Dual-Stack Application

**Frontend (SvelteKit + TypeScript)**
- Location: `src/` directory
- SPA built with SvelteKit using adapter-static
- TypeScript with strict type checking
- State management via Svelte stores (`src/lib/stores/`)
- API client layer in `src/lib/apis/`
- Component library in `src/lib/components/`

**Backend (FastAPI + Python)**
- Location: `backend/open_webui/`
- Python 3.11+ FastAPI application
- Entry point: `backend/open_webui/main.py`
- Router-based architecture in `backend/open_webui/routers/`
- Database models in `backend/open_webui/models/` using Peewee ORM
- SQLAlchemy for migrations (Alembic)

### Key Architectural Patterns

**API Communication**: Frontend makes REST API calls to backend at `/api/v1/*` endpoints. The frontend uses `WEBUI_API_BASE_URL` constant (from `src/lib/constants.ts`) to construct API URLs.

**Authentication**: JWT-based authentication with bearer tokens. Backend handles auth in `backend/open_webui/routers/auths.py`. Frontend APIs include token in Authorization header.

**Real-time**: Socket.io integration for real-time features (chat streaming, voice calls) via `backend/open_webui/socket/`.

**RAG Pipeline**: Document retrieval and embedding system in `backend/open_webui/retrieval/` with support for multiple vector databases (ChromaDB, Milvus, Qdrant, etc.).

**LiveKit Integration**: Voice/video call capabilities using LiveKit in `backend/livekit/` with separate workspace members for voice-agent and stt-agent.

**Database**: Supports SQLite (default), PostgreSQL, and MySQL. Connection configured via `DATABASE_URL` environment variable.

## Development Commands

### Frontend Development

```bash
# Start frontend dev server (requires backend running separately)
npm run dev

# Start on custom port
npm run dev:5050

# Build production frontend
npm run build

# Build in watch mode
npm run build:watch

# Type checking
npm run check
npm run check:watch

# Linting (runs all linters)
npm run lint

# Frontend-only linting
npm run lint:frontend

# Format code
npm run format

# Frontend tests
npm run test:frontend
```

### Backend Development

```bash
# Navigate to backend directory
cd backend

# Start backend dev server with hot reload
./dev.sh
# This runs: uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --forwarded-allow-ips '*' --reload

# Or manually:
python -m uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --reload

# Backend linting (from project root)
npm run lint:backend  # runs pylint

# Backend formatting (from project root)
npm run format:backend  # runs black
```

### Full Stack Development

For typical development, you need **both** servers running:

1. **Terminal 1 - Backend**: `cd backend && ./dev.sh`
2. **Terminal 2 - Frontend**: `npm run dev`

Frontend dev server (default port 5173) proxies API requests to backend (port 8080).

### Database

The backend automatically handles migrations on startup. Database file (if using SQLite) is stored in `backend/data/webui.db`.

### Environment Configuration

- Frontend: Uses `.env` file in project root (loaded by Vite)
- Backend: Uses `.env` file in project root (loaded via python-dotenv from `backend/open_webui/env.py`)
- See `.env.example` for available configuration options

## Important Development Notes

### Frontend-Backend Coordination

- Frontend API calls are in `src/lib/apis/[module]/index.ts`
- Backend routes are in `backend/open_webui/routers/[module].py`
- Models/schemas are defined separately in both:
  - Backend: `backend/open_webui/models/[module].py` (Peewee models + Pydantic schemas)
  - Frontend: TypeScript interfaces/types in API files or `src/lib/types/`

### Static File Building

The production build process (`npm run build`) creates static files in `build/` directory. The backend serves these static files when running in production mode (configured in `backend/open_webui/main.py`).

### Route Structure

**Frontend Routes** (SvelteKit file-based routing):
- Main app routes: `src/routes/(app)/`
- Auth routes: `src/routes/auth/`
- Layout: `src/routes/+layout.svelte`

**Backend Routes** (FastAPI routers):
- Mounted at `/api/v1/` prefix
- Each router file in `backend/open_webui/routers/` corresponds to an API module
- Example: `backend/open_webui/routers/chats.py` → `/api/v1/chats/*`

### Pyodide Integration

The frontend uses Pyodide for client-side Python execution (e.g., for Python tools/functions). Run `npm run pyodide:fetch` to download Pyodide files (automatically run before dev/build).

### Testing

- Frontend tests: Vitest (`npm run test:frontend`)
- E2E tests: Cypress (`npm run cy:open`)
- Backend tests: pytest (run from backend directory)

### i18n (Internationalization)

Translation files are in `src/lib/i18n/locales/`. To parse and update translations:

```bash
npm run i18n:parse
```

## Common Workflows

### Adding a New API Endpoint

1. Create/update router in `backend/open_webui/routers/`
2. Add Pydantic models if needed in `backend/open_webui/models/`
3. Create corresponding TypeScript API function in `src/lib/apis/`
4. Update TypeScript types as needed

### Adding a New Page/Route

1. Create `+page.svelte` in appropriate `src/routes/` subdirectory
2. Add `+page.ts` or `+page.server.ts` if data loading is needed
3. Update navigation components if needed

### Database Schema Changes

1. Modify Peewee model in `backend/open_webui/models/`
2. Create Alembic migration in `backend/open_webui/migrations/versions/`
3. Test migration locally before committing

## Technology Stack Summary

**Frontend**: SvelteKit 2.x, TypeScript 5.x, Tailwind CSS 4.x, Vite 5.x

**Backend**: FastAPI 0.115, Python 3.11+, Uvicorn, Peewee ORM, SQLAlchemy (migrations)

**AI/ML**: LangChain, Transformers, sentence-transformers, OpenAI SDK, Anthropic SDK

**Vector Stores**: ChromaDB, Qdrant, Milvus, Pinecone, OpenSearch, Elasticsearch

**Real-time**: Socket.io, LiveKit (voice/video)

**Build Tools**: Node.js 18.13-22.x, npm 6+

## Package Management

This project uses both npm (frontend) and pip/uv (backend):

- **Frontend**: `package.json` and `package-lock.json`
- **Backend**: `pyproject.toml` and `uv.lock` (using uv) or pip with `backend/requirements.txt`

## Docker Deployment

Multiple Docker Compose configurations available:
- `docker-compose.yaml` - Standard deployment
- `docker-compose-ollama.yaml` - With bundled Ollama
- See README.md for full Docker deployment options
