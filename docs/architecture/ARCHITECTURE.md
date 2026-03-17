# Architecture Overview

This document describes the technical architecture of the PrismA - Secure Journal App.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Frontend)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Templates  │  │  Tailwind    │  │    JavaScript        │  │
│  │   (Jinja2)   │  │  CSS (CDN)   │  │  (Vanilla + Chart.js)│  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼────────────────────────────────────┐
│                     Flask Application                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Routes     │  │  API         │  │   Context            │  │
│  │   (Pages)    │  │  Endpoints   │  │   Processors         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────┬─────────────────┬─────────────────────┬─────────────────┘
        │                 │                     │
┌───────▼───────┐ ┌───────▼───────┐ ┌───────────▼───────────────┐
│   Database    │ │   Utilities   │ │     External Services     │
│   (SQLite)    │ │   (AI, Voice) │ │   (Ollama, Whisper, SD)   │
└───────────────┘ └───────────────┘ └───────────────────────────┘
```

## Directory Structure

```
journalapp/
├── app/
│   ├── app.py              # Main Flask application
│   ├── database/
│   │   ├── db.py           # SQLite operations
│   │   ├── journal.db      # Database file (runtime)
│   │   └── chroma/         # Vector store (runtime)
│   ├── models/
│   │   └── vector_store.py # ChromaDB wrapper
│   ├── templates/          # Jinja2 HTML templates
│   ├── static/
│   │   ├── css/            # Custom styles
│   │   ├── js/             # Client-side JavaScript
│   │   └── uploads/        # Generated artwork
│   └── utils/
│       ├── ai.py           # Ollama LLM integration
│       ├── voice.py        # Whisper transcription
│       ├── image_gen.py    # Stable Diffusion
│       ├── services.py     # Service health checks
│       ├── errors.py       # Error handling
│       ├── cache.py        # Query caching
│       └── rate_limit.py   # API rate limiting
├── config.py               # Configuration management
├── requirements.txt        # Python dependencies
└── .env.example            # Environment template
```

## Database Schema

### Core Tables

**entries** - Journal entries
- `id` (UUID, PK) - Unique identifier
- `created_at`, `modified_at` - Timestamps
- `content` - Entry text
- `word_count`, `writing_duration` - Metrics
- `entry_type` - text, voice, framework, scan
- `framework_id` (FK) - Optional framework reference
- `summary` - AI-generated summary
- `artwork_path`, `artwork_style` - Image metadata

**emotions** - Plutchik's emotion wheel
- `entry_id` (FK) - Links to entry
- `emotion` - joy, trust, fear, surprise, sadness, disgust, anger, anticipation
- `intensity` - low, medium, high
- `frequency` - 0.0 to 1.0

**tags** - Entry tags (normalized, lowercase)

**frameworks** - Journaling templates
- `name`, `description`, `category`
- `questions` - JSON array of question objects

**embeddings** - Semantic search vectors
- `entry_id` (FK)
- `embedding_vector` - JSON array of floats
- `model_version` - Tracks embedding model

**settings** - Key-value configuration store

**prompts** - Writing prompts by category

### Indexes

Optimized for common queries:
- `idx_entries_created_at` - Timeline sorting
- `idx_entries_entry_type` - Type filtering
- `idx_emotions_entry_id` - Emotion lookups
- `idx_tags_entry_id` - Tag lookups
- Composite indexes for filtered queries

## Service Architecture

### Graceful Degradation

Each external service is optional. The app checks availability at startup and adapts:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Service Status Check                          │
│                                                                   │
│  Ollama    ──► Available?  ─► Yes: AI features enabled          │
│                             └► No:  Fallback to basic analysis  │
│                                                                   │
│  Whisper   ──► Available?  ─► Yes: Voice input enabled          │
│                             └► No:  Voice button hidden         │
│                                                                   │
│  ChromaDB  ──► Available?  ─► Yes: Semantic search enabled      │
│                             └► No:  Keyword search only         │
│                                                                   │
│  Stable    ──► Available?  ─► Yes: AI artwork generation        │
│  Diffusion                  └► No:  Algorithmic/SVG fallback    │
└─────────────────────────────────────────────────────────────────┘
```

### Service Initialization Flow

```python
# services.py - init_services()
1. Check Ollama → GET /api/tags
2. Check Whisper → import whisper
3. Check ChromaDB → Initialize collection
4. Check Embeddings → import sentence_transformers
5. Check SD → GET /sdapi/v1/sd-models
```

## API Design

### Page Routes (HTML)

| Route | Description |
|-------|-------------|
| `GET /` | Dashboard |
| `GET /entry/new` | New entry form |
| `GET /entry/<id>` | View entry |
| `GET /journal` | Entry list |
| `GET /settings` | Configuration |
| `GET /search` | Search page |
| `GET /status` | System diagnostics |

### API Endpoints (JSON)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | AI entry analysis |
| `/api/transcribe` | POST | Voice transcription |
| `/api/generate/artwork` | POST | Image generation |
| `/api/search/semantic` | POST | Vector search |
| `/api/memory/similar` | POST | Find similar entries |
| `/api/insights/*` | GET | Analytics data |

## Key Design Decisions

### Local-First

All data stays on the user's machine:
- SQLite for structured data
- ChromaDB for vectors
- Local file storage for images
- No external API calls for core functionality

### UUID Entry IDs

Entries use UUIDs instead of auto-increment integers:
- Enables offline-first sync (future)
- No ID collisions across devices
- Privacy-preserving (no sequential patterns)

### Lazy Model Loading

Heavy models load on-demand:
- Whisper loads on first transcription
- Embedding model loads on first search
- Reduces startup time significantly

### Template-Driven UI

Jinja2 templates with Tailwind CSS:
- Server-side rendering for fast initial load
- Dynamic theming via CSS variables
- Progressive enhancement with JavaScript

## Performance Optimizations

### Caching

- TTL-based query cache for aggregations
- LRU cache for embeddings
- localStorage for user preferences

### Database

- Batch loading for emotions/tags (avoids N+1)
- Indexed columns for common filters
- Connection-per-request pattern

### Rate Limiting

Per-endpoint limits prevent abuse:
- Analysis: 10/minute
- Transcription: 5/minute
- Image generation: 3/minute

## Security Considerations

- Input validation on all endpoints
- Content length limits
- Rate limiting
- No external data transmission
- SQL injection prevention (parameterized queries)
- XSS prevention (Jinja2 auto-escaping)
