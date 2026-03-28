# LM Studio Support Feature

## Overview
This branch adds native LM Studio support as an alternative to Ollama for LLM functionality. Users can now choose between Ollama and LM Studio via configuration.

## Changes Made

### 1. Configuration (`config.py`)
- Added `LLM_PROVIDER` setting (default: "ollama")
- Added `LMSTUDIO_BASE_URL` (default: "http://localhost:1234/v1")
- Added `LMSTUDIO_MODEL` (default: "local-model")
- Added `LMSTUDIO_TIMEOUT` (default: 120)

### 2. Service Status (`app/utils/services.py`)
- Added `check_lmstudio()` function to verify LM Studio connection
- Updated `ServiceStatus` class to track both Ollama and LM Studio
- Modified status display to show active provider with `[ACTIVE]` marker
- Both providers are always checked; active one is highlighted

### 3. AI Integration (`app/utils/ai.py`)
- Added `_make_lmstudio_request()` for OpenAI-compatible API calls
- Added `_chat_with_lmstudio()` for LM Studio-specific logic
- Modified `chat_with_ollama()` to route to correct provider based on `LLM_PROVIDER`
- Maintains backward compatibility - all existing functions work unchanged

### 4. Settings UI (`app/templates/settings.html`)
- Added LLM Provider dropdown (Ollama / LM Studio)
- Added LM Studio endpoint configuration field
- Added LM Studio model name configuration field
- Organized LLM settings into logical sections

### 5. App Routes (`app/app.py`)
- Added new settings to defaults: `llm_provider`, `lmstudio_base_url`, `lmstudio_model`
- Settings are persisted in database and can be changed via UI

### 6. Environment Variables (`.env.example`)
- Documented new LM Studio configuration options
- Added usage instructions and download link

## Usage

### Using Ollama (default)
```bash
# In .env or environment
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Or via command line
python app/app.py --ollama
```

### Using LM Studio
```bash
# In .env or environment
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=llama-3.2-3b-instruct  # Use actual model ID from LM Studio

# Or via command line
python app/app.py --lmstudio
```

### Command-Line Override (Recommended for Multi-Developer Teams)
You can override the LLM provider without changing `.env`:

```bash
# Quick flags
python app/app.py --ollama          # Force Ollama
python app/app.py --lmstudio        # Force LM Studio

# Alternative syntax
python app/app.py --llm ollama
python app/app.py --llm lmstudio

# Custom port/host
python app/app.py --lmstudio --port 8080 --host 127.0.0.1

# View all options
python app/app.py --help
```

**Benefits:**
- ✅ No need to edit `.env` or config files
- ✅ Each developer can use their preferred LLM without conflicts
- ✅ Easy to switch for testing
- ✅ Works alongside environment variables (CLI takes precedence)

### Switching Providers
1. Open Settings page in the app
2. Select "LM Studio" from the LLM Provider dropdown
3. Configure LM Studio endpoint and model name
4. Save settings
5. Restart the app for changes to take effect

## API Differences

### Ollama API
- Endpoint: `/api/generate`
- Format: `{"model": "...", "prompt": "...", "system": "..."}`
- Response: `{"response": "..."}`

### LM Studio (OpenAI-compatible) API
- Endpoint: `/chat/completions`
- Format: `{"model": "...", "messages": [{"role": "system"/"user", "content": "..."}]}`
- Response: `{"choices": [{"message": {"content": "..."}}]}`

## Testing

Both providers are checked on startup. Check the console logs:
```
[INFO] utils.services:   Active LLM Provider: OLLAMA
[INFO] utils.services:   Ollama (LLM) [ACTIVE]      [OK] Connected — model 'llama3.2' available
[INFO] utils.services:   LM Studio (LLM)            [UNAVAILABLE] Cannot connect...
```

Or with LM Studio active:
```
[INFO] utils.services:   Active LLM Provider: LMSTUDIO
[INFO] utils.services:   Ollama (LLM)               [UNAVAILABLE] Cannot connect...
[INFO] utils.services:   LM Studio (LLM) [ACTIVE]   [OK] LM Studio is running. Available models: ...
```

## Files Modified
- `config.py` - Added LM Studio config variables
- `app/utils/services.py` - Added LM Studio health check
- `app/utils/ai.py` - Added LM Studio API support with OpenAI format
- `app/app.py` - Added settings defaults + **argparse CLI support**
- `app/templates/settings.html` - Added UI controls
- `.env.example` - Documented new variables
- `README.md` - Updated configuration table and usage examples
- `start.ps1` - Added argument pass-through support
- `.gitignore` - Added patterns for personal dev scripts
- `docs/setup/CLI_USAGE.md` - Complete command-line guide (NEW)
- `docs/features/LM_STUDIO_FEATURE.md` - This file (NEW)

## Backward Compatibility
✅ All existing code works without changes
✅ Default behavior unchanged (uses Ollama)
✅ No breaking changes to API or database schema
✅ CLI arguments are optional - everything works without them
