# Localization System

## Quick Start

### Set Language

**Option 1: Environment Variable**
```bash
# In .env file or environment
DEFAULT_LANGUAGE=en  # English 
DEFAULT_LANGUAGE=de  # German (default)
```

**Option 2: CLI flag**
```bash
python app\app.py --lang en
python app\app.py --lang de
```

### Use in Templates
```jinja
{{ t('ui.dashboard.new_entry') }}
{{ t('ui.filter.date_from') }}
```

### Use in Python Code
```python
from app.utils.i18n import get_prompt
from config import Config

prompt = get_prompt("prompt.my_new_prompt", Config.DEFAULT_LANGUAGE)
```

## Architecture

**i18n Module** (`app/utils/i18n.py`):
- Translation dictionaries for English & German
- `translate(key, lang, **kwargs)` – UI text
- `get_prompt(key, lang, **kwargs)` – AI prompts with `{response_language}` substitution
- `normalize_language(lang)` – Standardize language codes

**Configuration** (`config.py`):
- `DEFAULT_LANGUAGE` setting (env: `DEFAULT_LANGUAGE`)

**AI Prompts** (`ai.py`, `db.py`):
- Use `{response_language}` placeholder (auto-substituted based on `DEFAULT_LANGUAGE`)

**Templates**:
- Context processor injects `t()` function and `ui_language` variable
- Replace hardcoded text with `{{ t('key') }}`

## Adding Translations

Simply add to `app/utils/i18n.py`:

```python
TRANSLATIONS = {
    "en": {
        "ui.my_key": "English text",
        "prompt.my_prompt": "You are helpful. Use {response_language} for responses.",
    },
    "de": {
        "ui.my_key": "Deutscher Text",
        "prompt.my_prompt": "Du bist hilfreich. Nutze {response_language} für Antworten.",
    },
}
```

## Template Examples

**Dashboard** (before):
```html
<p>Was bewegt dich heute?</p>
<button>Neuer Eintrag</button>
```

**Dashboard** (after):
```html
<p>{{ t('ui.dashboard.hero') }}</p>
<button>{{ t('ui.dashboard.new_entry') }}</button>
```

Keys available: ~200+ for UI & prompts (see `app/utils/i18n.py`)
```

## Available Translation Keys

### UI Keys

Dashboard:
- `ui.dashboard.hero` - "What's on your mind today?"
- `ui.dashboard.new_entry` - "New Entry"
- `ui.dashboard.daily_reflection` - "Daily Reflection"
- `ui.dashboard.write_about` - "Write about this"
- `ui.dashboard.new_question` - "New Question"

Navigation:
- `ui.nav.dashboard` - "Dashboard"
- `ui.nav.journal` - "Journal"
- `ui.nav.search` - "Search"
- `ui.nav.insights` - "Insights"
- `ui.nav.settings` - "Settings"

Entry Form:
- `ui.entry.mood` - "Mood"
- `ui.entry.tags` - "Tags"
- `ui.entry.save` - "Save"
- `ui.entry.cancel` - "Cancel"
- `ui.entry.delete` - "Delete"

Filters:
- `ui.filter.date_from` - "From"
- `ui.filter.date_to` - "To"
- `ui.filter.emotions` - "Emotions"
- `ui.filter.tags` - "Tags"
- `ui.filter.apply` - "Apply Filters"

### Prompt Keys

All prompt keys are prefixed with `prompt.`:
- `prompt.analyze_entry`
- `prompt.suggest_title`
- `prompt.generate_image_prompt`
- `prompt.entry_metadata`
- `prompt.suggest_tags`
- `prompt.active_issues`
- And more...

## Adding a New Language

1. Add the language code to `TRANSLATIONS` in `i18n.py`:

```python
TRANSLATIONS = {
    "en": { ... },
    "de": { ... },
    "fr": {  # French
        "ui.dashboard.hero": "Qu'est-ce qui vous préoccupe aujourd'hui?",
        # ... add more translations
    },
}
```

2. Update the `lang_names` dictionary in `get_prompt()`:

```python
lang_names = {
    "en": "English",
    "de": "German"
}
```

3. Set `DEFAULT_LANGUAGE=fr` in your `.env` file

## Migration Notes

### What Was Changed

1. **`ai.py`**:
   - Removed `_DEFAULT_PROMPTS` dictionary
   - Modified `_get_prompt()` to use `get_prompt()` from i18n
   - All prompts now retrieved dynamically based on language setting

2. **`db.py`**:
   - Removed hardcoded German text from all system prompts
   - Replaced with English versions using `{response_language}` placeholder
   - Functions `_seed_system_prompts()` and `_backfill_system_prompts()` updated

3. **`config.py`**:
   - Added `DEFAULT_LANGUAGE` configuration

4. **`i18n.py`**:
   - Expanded with comprehensive translation keys
   - Added `get_prompt()` function for AI prompt translation
   - Includes both English and German translations

## Benefits

- ✅ No hardcoded language requirements in AI prompts
- ✅ Easy to switch between languages
- ✅ Extensible to any language
- ✅ Centralized translation management
- ✅ Type-safe with fallbacks to English
- ✅ AI responses automatically use configured language
- ✅ Templates can use simple `t()` function

## Future Enhancements

- User-specific language preferences (per-user setting)
- Browser language auto-detection
- Translation management UI
- Export/import translations as JSON
- Crowdsourced translations
- RTL (Right-to-Left) language support
