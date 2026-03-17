# Privacy Policy

This document explains how the PrismA - Secure Journal App handles your data.

## Core Principle: Local-First

**All your journal data stays on your computer.** This app is designed with privacy as a fundamental principle, not an afterthought.

## Data Storage

### What data is stored

| Data Type | Location | Purpose |
|-----------|----------|---------|
| Journal entries | `app/database/journal.db` | Your writing |
| Emotions & tags | Same database | Entry metadata |
| Embeddings | Same database + ChromaDB | Semantic search |
| Settings | Same database | Preferences |
| Generated images | `app/static/uploads/` | Entry artwork |

### Where data is stored

All data is stored locally in the project directory:
- **Database**: `app/database/journal.db` (SQLite file)
- **Vector store**: `app/database/chroma/` (ChromaDB)
- **Images**: `app/static/uploads/`

You can move, backup, or delete these files at any time.

## Data Transmission

### What is NOT sent externally

- Journal content
- Personal information
- Analytics or usage data
- Any identifiable information

### Local service communication

The app communicates with local services only:

| Service | Default Address | Purpose |
|---------|-----------------|---------|
| Ollama | localhost:11434 | AI text analysis |
| Stable Diffusion | localhost:7860 | Image generation |

These run on your machine. No internet connection is required for core functionality.

### Optional external connections

| Connection | When | Data Sent |
|------------|------|-----------|
| CDN (Tailwind CSS, Chart.js) | Page load | None (fetches libraries) |
| Model downloads | First use | None (downloads models) |

You can disable CDN usage by self-hosting the libraries.

## AI Processing

### Ollama (Text Analysis)

- Runs entirely on your machine
- No data leaves your computer
- Models are downloaded once and run locally
- Analysis results stored in your local database

### Whisper (Voice Transcription)

- Runs entirely on your machine
- Audio processed locally
- Transcriptions stored only if you save them
- No audio sent to external servers

### Stable Diffusion (Image Generation)

- Runs entirely on your machine (if enabled)
- Prompts derived from entry themes (not full content)
- Generated images stored locally
- No entry content sent to image generation

## Data Retention

You control how long data is kept:
- **Default**: Keep forever
- **Options**: 1 year, 2 years, or forever
- **How it works**: Entries older than the retention period are deleted on app startup

To change: Settings > Data Management > Data Retention Period

## Data Export

You can export all your data at any time:
- **JSON**: Complete structured export
- **Markdown**: Human-readable format
- **PDF**: Printable document

To export: Settings > Data Management > Export

## Data Deletion

### Delete specific entries
- Open entry > Delete button
- Or use bulk delete in Journal view

### Delete all data
- Settings > Data Management > Delete Everything
- Requires typing "DELETE" to confirm
- Permanently removes all entries, tags, emotions, embeddings

### Complete removal
To fully remove all traces:
1. Delete the database: `app/database/journal.db`
2. Delete the vector store: `app/database/chroma/`
3. Delete uploads: `app/static/uploads/`

## Security Measures

### Input validation
- All inputs sanitized before storage
- SQL injection prevention (parameterized queries)
- Content length limits enforced

### Access control
- App runs locally only (localhost)
- No authentication required (single-user design)
- No remote access by default

### Rate limiting
- API endpoints rate-limited
- Prevents accidental or malicious overload

## Third-Party Services

This app uses no third-party services for data processing. The only external resources are:
- **Tailwind CSS CDN** - Styling (no data transmitted)
- **Chart.js CDN** - Visualizations (no data transmitted)
- **jsPDF CDN** - PDF export (runs client-side)

## Your Rights

You have complete control over your data:

| Right | How to Exercise |
|-------|-----------------|
| Access | View any entry at any time |
| Export | Settings > Export (JSON, Markdown, PDF) |
| Delete | Delete individual entries or all data |
| Portability | Export and use data elsewhere |
| Modification | Edit any entry at any time |

## Changes to This Policy

This privacy policy may be updated with new versions of the app. Changes will be documented in release notes.

## Questions

For privacy-related questions, open an issue on the project repository.

---

**Summary**: Your journal is yours. We don't see it, store it, or transmit it. Everything runs locally on your machine.
