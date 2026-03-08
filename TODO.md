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
- [ ] **Localization / multi language support
  - Full English language support

---

## 🐛 Known Bugs

### Critical
- [ ] **Recurring Chinese characters in DeepSeek responses**
  - Issue: Chinese characters appearing where DeepSeek is used
  - Needs investigation and fix
  - Related to prompt/response handling

### Setup/Installing
- [x] **Requirements.txt: Error installing "openai-whisper" package**
  - Error during package installation
  - **Workaround documented:** `python -m pip install --no-build-isolation openai-whisper`
  - Consider: Adding to setup docs or fixing in requirements.txt

---

## ✅ Completed

### Recently Done
- **LM Studio Support**
  - Added LM Studio as alternative LLM provider
  - OpenAI-compatible API integration
  - Dual provider support (Ollama + LM Studio)
  - Provider selection in settings UI

- **CLI Arguments** 
  - Added `--ollama` and `--lmstudio` flags
  - Custom `--port` and `--host` options
  - Command-line provider override
  - Multi-developer workflow support

- **Documentation Organization**
  - Reorganized docs into `docs/` folder structure
  - Created `docs/features/` for feature docs
  - Created `docs/setup/` for setup guides
  - Updated README with doc links

- **Bug fixes/Other improvements**
  - Dashboard insights now skip expensive AI analysis when not enough entries exist
  - Prevented unnecessary Big Five, Baustellen, and recurring-topic generation on empty datasets
  - Reduced dashboard load blocking by deferring external D3 CDN script loading
  - Improved graceful fallback behavior when external CDN resources are unavailable
  - Added dark mode support and integrated it into the UI experience

---

## 📝 Notes
- LLM provider priority: CLI args > env vars > defaults


*Last Updated: 08.03.2026*
