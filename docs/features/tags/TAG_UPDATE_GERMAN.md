# Tag Auto-Suggestion Update - German & Animation

## Changes Made

### 1. German Language Support
- **Tag Generation**: AI now generates tags in German (e.g., `arbeit`, `stress`, `familie`)
- **UI Labels**: All interface text translated to German:
  - "Tags" → "Tags"
  - "Suggest Tags" → "Tags vorschlagen"
  - "Suggesting..." → "Vorschlagen..."
  - "Add tag (press Enter)" → "Tag hinzufügen (Enter drücken)"
  - "Suggested tags (click to add):" → "Vorgeschlagene Tags (zum Hinzufügen klicken):"
  - "No tags added yet..." → "Noch keine Tags hinzugefügt..."

### 2. Smart Suggestion Behavior
**Fixed**: Clicking a suggested tag no longer hides all other suggestions!

**New Behavior**:
- Click a suggested tag → It animates to the tags section with a smooth transition
- Other suggestions stay visible
- When you click all suggestions → System automatically fetches new ones
- Beautiful animations as tags move and space refills

### 3. Animations
**Tag Entering Animation**:
- New tags fade in with a "pop" effect (scale + translate)
- Smooth cubic-bezier easing for natural feel
- Duration: 300ms

**Tag Leaving Animation**:
- Suggestions slide out to the left while fading
- Container space smoothly collapses
- Other suggestions slide to fill the gap

**Hover Effects**:
- Suggestions lift up slightly on hover
- Subtle shadow appears
- Smooth color transition

### 4. Editable Prompt in Settings
**New**: You can now customize how tags are generated!

**How to Edit**:
1. Go to **Settings** → **System Prompts**
2. Find **"Tags & Organization"** category
3. Click **"Tag Extraction"**
4. Edit the prompt to your liking!

**Default German Prompt**:
```
Du bist ein Experte für die Extraktion von Schlagwörtern aus Texten. 
Analysiere diesen Tagebucheintrag und extrahiere 3-7 relevante Tags auf Deutsch.

Anforderungen:
- Tags sollten kleingeschrieben sein
- Mischung aus einzelnen Wörtern und kurzen Wortgruppen (max. 2 Wörter)
- Verwende Bindestriche für zusammengesetzte Begriffe: "arbeit-stress", "familienessen"
- Fokus auf: Themen, Emotionen, Aktivitäten, Beziehungen
- Priorisiere spezifische, bedeutungsvolle Kategorien
- Vermeide: der, und, tag, zeit, ding, fühlen, gefühlt, heute, denken

Beispiele für gute Tags: arbeit, angst, team-konflikt, deadline, kommunikation, arbeit-stress
Beispiele für schlechte Tags: heute, gefühlt, dinge, arbeit und leben

Gib NUR ein JSON-Array zurück wie: ["tag1", "tag2", "tag3"]
Keine Erklärung, kein Markdown, nur das JSON-Array.

Eintrag:
{content}
```

**Customization Options**:
- Change language (German, English, French, etc.)
- Modify tag style (single words only, phrases allowed, etc.)
- Adjust focus areas (more emotions, more activities, etc.)
- Add specific instructions (e.g., "always include location tags")

## Files Modified

1. `app/utils/ai.py`:
   - Added German `tag_extraction` prompt to `_DEFAULT_PROMPTS`
   - Updated `suggest_tags()` to use editable system prompt

2. `app/app.py`:
   - Added "Tags & Organization" category to prompt_categories

3. `app/templates/entry_form.html`:
   - Translated all UI text to German
   - Added animation functions (`renderTagsWithAnimation`, `removeSuggestionWithAnimation`)
   - Fixed suggestion disappearing bug
   - Added CSS animations in `<style>` block

## How It Works Now

### Example Flow:
1. **Type**: "Hatte heute ein stressiges Meeting mit meinem Chef."
2. **Pause**: Wait 0.5 seconds
3. **See Suggestions**: 
   ```
   [arbeit] [meeting] [stress] [chef] [kommunikation]
   ```
4. **Click** `[meeting]`:
   - Button slides left and fades out
   - Tag appears in your tags section with "pop" animation
   - Other suggestions stay visible
5. **Click More**: Add `arbeit` and `stress`
6. **Auto-Refresh**: When only 1 suggestion left, new ones appear!
   ```
   [team-konflikt] [deadline] [druck]
   ```

### Settings Customization:
- Go to Settings → System Prompts → Tags & Organization → Tag Extraction
- Edit to change tag style:
  ```
  # For only single-word tags:
  - Tags müssen einzelne Wörter sein (keine Bindestriche)
  
  # For workplace focus:
  - Priorisiere Tags über: Projekte, Kollegen, Meetings, Deadlines
  
  # For emotional focus:
  - Extrahiere vor allem emotionale Tags: glücklich, traurig, ängstlich, aufgeregt
  ```

## Testing

1. **Restart the app**:
   ```bash
   python app/app.py
   ```

2. **Create new entry** with German text:
   > "War heute im Fitnessstudio und habe mich danach viel besser gefühlt. Die Bewegung hilft gegen Stress."

3. **Wait 0.5 seconds** → See German suggestions:
   ```
   [fitnessstudio] [bewegung] [stress] [gesundheit] [wohlbefinden]
   ```

4. **Click suggestions** → Watch animations!

5. **Try Settings**:
   - Go to Settings → System Prompts
   - Edit the Tag Extraction prompt
   - Change it to request different tag styles
   - Create new entry → See different suggestions!

## Troubleshooting

**No German tags appearing?**
- Check that Ollama is running: `ollama serve`
- Verify qwen3:0.6b model is pulled: `ollama list`
- Check browser console for errors

**Prompt changes not working?**
- Changes are saved per-prompt in settings
- Must click "Save" on individual prompt in settings
- Restart not required, takes effect immediately

**Animations not smooth?**
- Check browser console for CSS errors
- Try refreshing page
- Ensure you're using a modern browser (Chrome/Firefox/Edge)

## Next Steps

Your tag system is now:
✅ **German language** - Native support for German tags
✅ **Smart behavior** - Suggestions persist until all used
✅ **Animated** - Smooth transitions and visual feedback
✅ **Customizable** - Edit the AI prompt in settings

Enjoy your enhanced journaling experience! 🎉
