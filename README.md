# PrismA - Secure Journal App

A local-first journaling web application with AI-powered insights, semantic search, and voice-to-text input.

## Features

- **Rich Journal Entries** - Write and organize journal entries with mood tracking and tags
- **AI Analysis** - Get AI-powered insights, reframes, and prompts via local LLM (Ollama)
- **Semantic Search** - Find related entries using ChromaDB vector search
- **Voice Input** - Dictate entries using Whisper speech-to-text
- **Image Generation** - Optional Stable Diffusion integration for entry artwork
- **Fully Local** - All data stays on your machine

## Prerequisites

- Python 3.10+
- **LLM Provider** (choose one):
  - [Ollama](https://ollama.ai/) installed and running with a model pulled (e.g. `ollama pull llama3.2`), OR
  - [LM Studio](https://lmstudio.ai/) installed and running with a model loaded
- FFmpeg (required by Whisper for audio processing)

## Setup

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run the app (development with hot reload)
python app/app.py

# Or specify LLM provider via command line
python app/app.py --ollama     # Use Ollama
python app/app.py --lmstudio   # Use LM Studio
python app/app.py --help       # See all options
```

The app runs at `http://localhost:5000`.

## Configuration

Set environment variables or edit `config.py`:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask session secret |
| `LLM_PROVIDER` | `ollama` | LLM backend: `ollama` or `lmstudio` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API endpoint |
| `LMSTUDIO_MODEL` | `local-model` | LM Studio model ID |
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `SD_API_URL` | `http://localhost:7860` | Stable Diffusion API |
| `SD_ENABLED` | `false` | Enable image generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model for embeddings |

## Documentation

- **[FAQ](docs/FAQ.md)** - Frequently asked questions
- **[Architecture](docs/ARCHITECTURE.md)** - Technical architecture overview
- **[Privacy](docs/PRIVACY.md)** - Data privacy and security

### Features
- **[LM Studio Support](docs/features/LM_STUDIO_FEATURE.md)** - Alternative LLM provider setup
- **[Tag Implementation](docs/features/TAG_IMPLEMENTATION.md)** - Auto-tagging system
- **[Prompts System](docs/features/PROMPTS_MAPPING.md)** - Prompt management

### Setup Guides
- **[CLI Usage](docs/setup/CLI_USAGE.md)** - Command-line arguments and options
- **[ComfyUI Setup](docs/setup/COMFY_SETUP.md)** - Image generation setup
- **[Claude Integration](docs/setup/CLAUDE.md)** - AI assistant integration

### Project Management
- **[TODO](TODO.md)** - Current tasks and roadmap
- **[Contributing](CONTRIBUTING.md)** - How to contribute
