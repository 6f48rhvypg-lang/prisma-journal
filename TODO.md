# PrismA Journal - TODO & Project Tracking

## 🎯 Project Ideas / Features

### High Priority
- [ ] **Daily Reflection: Deep dive after 3+ entries**
  - Implement deeper reflection prompts when user has 3+ entries
  - Analyze patterns across multiple entries
  - Generate personalized follow-up questions

- [ ] **New Entry: Automatic tags & manual tags**
  - Add automatic tag suggestion system
  - Allow manual tag override/editing
  - Improve tag relevance algorithm

- [ ] **New Entry: Automatic artwork matching entry content**
  - Generate artwork automatically based on entry content
  - Option for manual artwork trigger
  - Artwork style selection

### Medium Priority
- [ ] **Dashboard: Expand emotional state visualization**
  - Expand emotional state visualization
  - Add trend analysis over time
  - More detailed emotion breakdown

- [ ] **Dashboard: Redesign date filtering in "Your Personality" section**
  - Redesign date filtering interface
  - Add preset date ranges (last week, month, year)
  - Improve filter UX

### Low Priority


---



## In Progress 


---

## 🐛 Known Bugs

### Critical
- []

### High
- [] **Recurring Chinese characters in DeepSeek responses**
  - Issue: Chinese characters appearing where DeepSeek is used
  - Needs investigation and fix
  - Related to prompt/response handling

### Setup/Installing
- [] **Requirements.txt: Error installing "openai-whisper" package**
  - Error during package installation
  - Only for Python 3.13 and above
  - **Workaround documented:** `python -m pip install --no-build-isolation openai-whisper`
  - Consider: Adding to setup docs or fixing in requirements.txt

### UI
  - Colors should be more fitting to the background, it's hard to see text sometimes


---

## ✅ Completed

### Recently Done
- **Dashboard Suggestions: Last Week visibility fix**
  - "Last week" label in Suggestions now only appears when enough recent entries are available
  - Added backend gating based on last 7 days entry count

- **Entry Artwork Reset/Delete**
  - Added delete/reset button in `/entry/<id>` under "Entry Artwork"
  - Added backend endpoint `POST /api/delete/artwork`
  - Clearing artwork now resets `artwork_path` and `artwork_style` to empty state
  - Added EN/DE i18n keys for delete confirm, loading, success, and error states

- **LM Studio Support**
  - Added LM Studio as alternative LLM provider
  - OpenAI-compatible API integration
  - Dual provider support (Ollama + LM Studio)
  - Provider selection in settings UI

- **CLI Arguments**
  - Added `--ollama`, `--lmstudio` and `--lang` flags
  - Custom `--port` and `--host` options
  - Command-line provider override
  - Multi-developer workflow support

- **Documentation Organization**
  - Reorganized docs into `docs/` folder structure
  - Created `docs/features/` for feature docs
  - Created `docs/setup/` for setup guides
  - Updated README with doc links

- **Localization/Internationalization**
  - Full English localization
  - Full German localization
  - Multi-language UI support

- **Bug fixes/other improvements**
  - Dashboard insights now skip expensive AI analysis when not enough entries exist
  - Prevented unnecessary Big Five, Baustellen, and recurring-topic generation on empty datasets
  - Reduced dashboard load blocking by deferring external D3 CDN script loading
  - Improved graceful fallback behavior when external CDN resources are unavailable
  - Added dark mode support and integrated it into the UI experience

---

## 📝 Notes
- LLM provider priority: CLI args > env vars > defaults


*Last Updated: 17.03.2026*
