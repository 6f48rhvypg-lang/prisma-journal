# Frequently Asked Questions

## General

### What is this app?

A local-first secure journaling application. It combines traditional journaling with AI-powered insights, emotion tracking, and semantic search - all running locally on your machine.

### Is my data private?

Yes. All data stays on your computer:
- Journal entries are stored in a local SQLite database
- AI processing uses local models (Ollama)
- No data is sent to external servers
- See [PRIVACY.md](../legal/PRIVACY.md) for details

### What are the system requirements?

- Python 3.10+
- 8GB RAM minimum (16GB recommended for larger models)
- 5GB free disk space
- GPU optional but improves AI performance

## Setup

### How do I install Ollama?

1. Download from [ollama.ai](https://ollama.ai/)
2. Install and run Ollama
3. Pull a model: `ollama pull llama3.2`
4. The app will auto-detect it

### Why isn't voice input working?

Check these:
1. Microphone permissions in your browser
2. Whisper model installed (`pip install openai-whisper`)
3. FFmpeg installed (required by Whisper)
4. Check `/status` page for service health

### How do I enable image generation?

1. Install [AUTOMATIC1111 Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
2. Run it with `--api` flag
3. Set in `.env`: `SD_ENABLED=true`
4. Set endpoint: `SD_ENDPOINT=http://localhost:7860`

## Features

### What are frameworks?

Journaling templates that guide your reflection with structured questions. Examples:
- CBT Thought Record
- Gratitude Practice
- Stoic Reflection
- Goal Setting

### How does emotion analysis work?

The app uses Plutchik's Wheel of Emotions to detect 8 base emotions:
- Joy, Trust, Fear, Surprise
- Sadness, Disgust, Anger, Anticipation

Each emotion has intensity (low/medium/high) and frequency (0-1 score).

### What is semantic search?

Unlike keyword search, semantic search finds entries by meaning. Ask questions like:
- "When was I last stressed about work?"
- "Times I felt proud"
- "Entries about my relationship"

Uses ChromaDB and sentence-transformers for vector similarity.

### How does the "Go Deeper" feature work?

When writing, click "Go Deeper" to get AI-generated follow-up questions that help you explore your thoughts more thoroughly. Questions adapt based on what you've already written.

## Troubleshooting

### The app won't start

1. Check Python version: `python --version` (need 3.10+)
2. Activate virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Check for error messages in terminal

### AI features aren't working

1. Ensure Ollama is running: `ollama serve`
2. Check the model is available: `ollama list`
3. Visit `/status` to see service health
4. The app works with reduced features if Ollama is unavailable

### Search isn't finding entries

1. New entries need a moment to be indexed
2. For semantic search, ChromaDB must be running
3. Try keyword search as a fallback
4. Check `/status` for ChromaDB status

### Images aren't generating

1. Stable Diffusion WebUI must be running with `--api` flag
2. Check `SD_ENABLED=true` in `.env`
3. Visit `/status` to verify connection
4. The app will use placeholder images if SD is unavailable

## Data Management

### How do I backup my journal?

Multiple options:
1. **Settings > Export > JSON** - Full data export
2. **Copy the database file** - `app/database/journal.db`
3. **Export to Markdown** - Human-readable backup

### How do I restore from backup?

1. Stop the app
2. Replace `app/database/journal.db` with your backup
3. Restart the app

### Can I import from other apps?

Currently manual import only. Export from your other app as text, then create new entries. Future versions may add import tools.

### How does data retention work?

In Settings > Data Management:
- **Keep forever** - No automatic deletion
- **Keep 1 year** - Entries older than 365 days deleted on startup
- **Keep 2 years** - Entries older than 730 days deleted on startup

Always backup before changing this setting!

## Customization

### How do I change the color theme?

Settings > Appearance > Color Theme. Choose from:
- Ocean, Forest, Sunset, Lavender, Slate, Sand, Berry

### Can I create custom frameworks?

Yes! Settings > Custom Frameworks. Define:
- Framework name
- Description
- Questions (JSON format)
- Category

### How do I change the AI model?

Set `OLLAMA_MODEL` in `.env` or Settings. Any Ollama-compatible model works:
- `llama3.2` (default, good balance)
- `llama3.2:1b` (faster, less capable)
- `mistral` (alternative)

## Performance

### The app is slow

Try these:
- Use a smaller Whisper model (tiny or base)
- Use a smaller LLM model
- Ensure adequate RAM
- Check if services are responding (visit `/status`)

### Analysis takes too long

AI analysis typically takes 15-30 seconds. To speed up:
- Use a smaller model
- Use a GPU with Ollama
- Reduce entry length before analysis

## Security

### Is it safe to use?

Yes. The app:
- Runs entirely locally
- Doesn't transmit data externally
- Uses SQLite with parameterized queries
- Validates all inputs
- Rate-limits API endpoints

See [PRIVACY.md](../legal/PRIVACY.md) for complete privacy information.
