# GEMINI.md - RAG Engine Project Context

## 1. Project Overview

**Name:** `rag-engine`
**Description:** A backend engine for a RAG (Retrieval-Augmented Generation) system, designed to work with Supabase, Cloudflare R2, and a custom RAG implementation ("LightRAG").
**Phase:** Currently in Phase 1 (Skeleton & Infrastructure).

### Architecture
The project follows a layered architecture (similar to Clean Architecture):
*   **API Layer (`server/app/api`):** FastAPI routes handling HTTP requests.
*   **Service Layer (`server/app/services`):** Business logic, including integrations with external services (R2, Document AI, RAG Engine).
*   **Data Layer (`server/app/db`):** Database access using SQLAlchemy (Async) and Supabase Postgres.
*   **Core (`server/app/core`):** Configuration, logging, and security (Supabase Auth).

### Key Technologies
*   **Language:** Python 3.11+
*   **Web Framework:** FastAPI
*   **Database:** PostgreSQL (via Supabase), SQLAlchemy (Async), asyncpg.
*   **Migrations:** Alembic
*   **Storage:** Cloudflare R2 (via boto3)
*   **Authentication:** Supabase Auth (JWT)
*   **Dependency Management:** Poetry

## 2. Directory Structure

*   `server/app/`: Main application source code.
    *   `main.py`: Application entry point.
    *   `api/`: Route definitions (`/me`, `/workspaces`, `/documents`, etc.).
    *   `core/`: Config (`config.py`), Security (`security.py`), Logging (`logging.py`).
    *   `db/`: Database models, session management, and repositories.
    *   `schemas/`: Pydantic models for request/response validation.
    *   `services/`: Logic for R2 storage, RAG engine interface, etc.
    *   `workers/`: Background workers for parsing and ingestion.
*   `alembic/`: Database migration scripts.
*   `docs/`: Comprehensive project documentation.
    *   `design/`: Architecture and phase-specific designs.
    *   `requirements/`: Product requirements.
    *   `implement/`: Implementation logs (Crucial for tracking progress).
*   `client/`: Placeholder for future frontend code.

## 3. Development Workflow

### Prerequisites
*   Python 3.11+
*   Poetry
*   `.env` file configured with Supabase and R2 credentials (see `.env.example`).

### Key Commands

**1. Installation**
```bash
poetry install
```

**2. Run Development Server**
```bash
poetry run uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
```

**3. Database Migrations**
*   Create a new migration: `poetry run alembic revision --autogenerate -m "message"`
*   Apply migrations: `poetry run alembic upgrade head`

**4. Testing**
*   **Unit/Integration:** `poetry run pytest` (if tests exist).
*   **Manual API Testing:** See `TESTING.md` for `curl` commands.

### Implementation Guidelines
*   **Documentation:** Before starting a task, review `docs/requirements` and `docs/design`.
*   **Logging:** After completing a significant task, update `docs/implement/` with a new log file following the template in `docs/implement/README.md`.
*   **Style:** Follow the existing coding style (snake_case for functions/vars, PascalCase for classes). Use Pydantic for data validation.
*   **Database:** Use SQLAlchemy Core/Async. Do NOT use ORM relationships unless strictly necessary; prefer explicit joins or repository methods.
*   **External Services:** Always use the wrapper services in `server/app/services/` instead of calling external APIs (R2, etc.) directly.

## 4. Current State (Phase 1)
*   Basic infrastructure is set up (FastAPI, DB connection, R2 wrapper).
*   Core entities (Workspaces, Documents, Conversations) have database tables and basic CRUD APIs.
*   Authentication via Supabase JWT is implemented.
*   Background workers (Parse, Ingest) are stubbed out or in early stages.

## 5. Important Files
*   `server/app/main.py`: Entry point.
*   `server/app/core/config.py`: Environment configuration.
*   `docs/design/architecture-overview.md`: High-level architecture reference.
*   `AGENTS.md`: Specific instructions for AI agents working on this repo.
