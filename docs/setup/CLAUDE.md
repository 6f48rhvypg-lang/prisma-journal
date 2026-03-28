# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A local-first secure journaling web app with AI-powered analysis, semantic search, voice input, and optional image generation. All data stays on the user's machine.

## Tech Stack

- **Backend:** Python Flask (app/app.py)
- **Frontend:** Jinja2 templates, Tailwind CSS (CDN), vanilla JavaScript
- **Database:** SQLite (app/database/journal.db, created at runtime)
- **Vector Store:** ChromaDB (app/database/chroma/, persistent)
- **AI:** Ollama (local LLM), Whisper (speech-to-text), Stable Diffusion (optional image gen)
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2 by default, used by ChromaDB)

## Commands

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
cp .env.example .env           # then edit .env as needed

# Run (development with hot reload)
python app/app.py

# The app runs at http://localhost:5000
# Ollama must be running for AI features (ollama serve)
```

## Architecture

### Configuration System
`config.py` (project root) — Loads `.env` via python-dotenv, then defines the `Config` class. Every setting has an environment variable override. Also exports module-level constants: `COLOR_THEMES` (5 palettes), `ARTWORK_STYLES` (8 styles), `WHISPER_MODELS`.

Key env vars: `DB_PATH`, `MODEL_PATH`, `WHISPER_MODEL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `SD_ENDPOINT`, `SD_ENABLED`, `SD_DEFAULT_STYLE`, `EMBEDDING_MODEL`, `CHROMA_COLLECTION`, `COLOR_THEME`, `DEBUG_MODE`, `MAX_ENTRY_LENGTH`, `OLLAMA_TIMEOUT`. See `.env.example` for the full list with defaults.

`Config.validate()` returns a list of `(field, warning_message)` tuples for invalid enum values or unreasonable limits. `Config.get_theme_colors()` returns the active color palette dict.

### Service Initialization & Graceful Degradation
`app/utils/services.py` — `init_services()` is called once at startup. It probes Ollama, Whisper, ChromaDB, sentence-transformers, and Stable Diffusion, populating a module-level `ServiceStatus` singleton. Each utility module (ai.py, voice.py, image_gen.py, vector_store.py) checks `status.<service>` before attempting work and returns error strings or no-ops when a service is unavailable. The app runs with reduced functionality rather than crashing.

`POST /api/services/refresh` re-runs all health checks live from the settings page.

### Entry Point & Routing
`app/app.py` — Single Flask application file. Calls `init_services()` then `init_db()` at startup. A `@app.context_processor` injects `theme_colors`, `theme_name`, and `service_status` into every template. All routes and API endpoints are defined here. The app adds the project root to `sys.path` so that `config`, `database`, `models`, and `utils` can be imported.

### Database Layer
`app/database/db.py` — All SQLite operations. Uses `sqlite3.Row` for dict-like access. Tables auto-created via `init_db()` at startup. Default prompts and frameworks seeded on first run.

**Schema (6 tables):**
- `entries` — UUID primary key, content, word_count, writing_duration, entry_type (text/voice/framework/scan), framework_id FK, summary (AI-generated), artwork_path, artwork_style
- `emotions` — Plutchik's 8 base emotions per entry with intensity (low/medium/high) and frequency (0-1 float)
- `tags` — Normalized tag names per entry (stored lowercase)
- `frameworks` — Journaling templates with JSON question arrays and categories
- `embeddings` — JSON-serialized vectors per entry with model_version tracking
- `settings` — Key/value store for app configuration

Entry IDs are UUID strings (not integers). `get_entry()` and `get_all_entries()` return dicts with `emotions` (list of dicts) and `tags` (list of strings) attached. Cascade deletes handle cleanup. `insert_sample_data()` populates 5 test entries with emotions and tags.

### Vector Store
`app/models/vector_store.py` — ChromaDB wrapper for semantic search. Lazy-initializes a persistent client using `Config.CHROMA_COLLECTION`. Entries are upserted with `entry_{id}` document IDs. Uses cosine similarity. Returns empty results when ChromaDB is unavailable.

### AI Utilities
- `app/utils/ai.py` — Ollama integration. Checks `status.ollama` before calling. Uses `Config.OLLAMA_TIMEOUT`. `generate_image_prompt()` incorporates `Config.SD_DEFAULT_STYLE`.
- `app/utils/voice.py` — Whisper transcription. Checks `status.whisper` before loading. Returns error strings on failure.
- `app/utils/image_gen.py` — Stable Diffusion WebUI API integration. Checks both `Config.SD_ENABLED` and `status.stable_diffusion`. Appends the configured artwork style to prompts.

### Frontend
Templates use Jinja2 with Tailwind CSS via CDN. The `base.html` template reads `theme_colors` from the context processor to configure Tailwind's primary palette dynamically — changing `COLOR_THEME` in `.env` or the settings page switches the entire color scheme. The nav bar shows an "LLM offline" indicator when Ollama is unavailable.

### API Endpoints (JSON)
All prefixed with `/api/`:
- `POST /api/analyze` — AI analysis of entry content
- `POST /api/suggest-title` — AI title suggestion
- `POST /api/transcribe` — Whisper audio transcription
- `POST /api/generate-image` — Stable Diffusion image generation
- `GET /api/prompt` — Random journal prompt
- `POST /api/services/refresh` — Re-check all service availability

### Key Patterns
- Entry IDs are UUID strings; routes use `<entry_id>` (not `<int:entry_id>`)
- Emotions and tags are separate tables, not columns on entries; `get_entry()` joins them automatically
- Templates display `entry.summary` (AI-generated) as the heading, falling back to truncated content
- All services use graceful degradation — check `services.status.<name>` before calling, return error strings or no-op on failure
- SQLite connections are opened/closed per function call (no connection pooling)
- ChromaDB collection and Whisper model are lazy-initialized as module-level singletons
- Vector store indexes entry content on create/edit, deletes on entry removal
- `Config.validate()` warns on invalid enum values at startup; does not block the app
