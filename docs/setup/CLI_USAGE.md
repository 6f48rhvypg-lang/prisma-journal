# Command-Line Usage Guide

## Quick Start

```bash
# Default (uses .env setting)
python app/app.py

# Force Ollama
python app/app.py --ollama

# Force LM Studio
python app/app.py --lmstudio

# Alternative syntax
python app/app.py --llm ollama
python app/app.py --llm lmstudio

# Custom port/host
python app/app.py --port 8080
python app/app.py --host 127.0.0.1
python app/app.py --lmstudio --port 8080

# View all options
python app/app.py --help
```

## Using with start.ps1 (Windows)

```powershell
# Default
.\start.ps1

# With LM Studio
.\start.ps1 --lmstudio

# With custom port
.\start.ps1 --port 8080
```

## Multi-Developer Workflow

**Scenario:** Two developers sharing a repository
- Developer A prefers Ollama
- Developer B prefers LM Studio

**Solution:**
1. Keep `.env` with default (e.g., `LLM_PROVIDER=ollama`)
2. Each developer runs with their preferred flag:
   ```bash
   # Developer A
   python app/app.py --ollama
   
   # Developer B  
   python app/app.py --lmstudio
   ```

3. Or create personal launch scripts:
   ```bash
   # dev-a-start.sh
   python app/app.py --ollama
   
   # dev-b-start.sh
   python app/app.py --lmstudio
   ```

4. Add `dev-*-start.*` to `.gitignore` so they don't conflict

## Priority Order

The LLM provider is determined in this order (highest to lowest):

1. **Command-line argument** (`--ollama`, `--lmstudio`, `--llm`)
2. **Environment variable** (`LLM_PROVIDER=...`)
3. **Default** (`ollama`)

This means CLI arguments always win, perfect for quick testing without changing configs.

## Examples

```bash
# Test different providers quickly
python app/app.py --ollama     # Test with Ollama
python app/app.py --lmstudio   # Test with LM Studio

# Run on different port for parallel testing
python app/app.py --ollama --port 5001 &
python app/app.py --lmstudio --port 5002 &

# Production deployment (respects .env)
python app/app.py

# Development with override
python app/app.py --lmstudio --host 127.0.0.1
```

## Checking Active Provider

Look for this line in the console output:

```
[CLI Override] LLM Provider set to: lmstudio
```

Or check the service status logs:

```
[INFO] utils.services:   Active LLM Provider: LMSTUDIO
```
