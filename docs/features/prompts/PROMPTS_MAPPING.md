# System Prompts Mapping Document

## Overview
This document maps all system prompts to their usage locations, triggers, and purposes within the journal application.

## Total Prompts: 19

---

## 📓 Journal Entry Page (Entry Creation & Viewing)
**Location:** `entry_form.html`, `entry_view.html`  
**Purpose:** AI analysis and enhancement of individual journal entries

### 1. `analyze_entry`
- **Where:** Entry view page - "Analyze" button
- **When:** User clicks "Analyze" or "Re-analyze" button
- **Why:** Provides comprehensive entry analysis including emotional tone, key themes, cognitive patterns, reframes, and follow-up prompts
- **Returns:** Human-readable analysis text

### 2. `generate_summary_and_title`
- **Where:** Entry form - "Finish Entry" flow
- **When:** After entry is saved, during the analysis pipeline
- **Why:** Automatically generates a concise title (max 8 words) and 2-3 sentence summary
- **Returns:** JSON with `title`, `summary`, `themes`

### 3. `detect_emotions`
- **Where:** Entry form - "Finish Entry" flow
- **When:** During the 4-step analysis pipeline (Step 1)
- **Why:** Uses Plutchik's wheel to detect joy, trust, fear, surprise, sadness, disgust, anger, anticipation
- **Returns:** JSON array of emotions with intensity, frequency, and supporting passages

### 4. `identify_patterns`
- **Where:** Entry form - "Finish Entry" flow  
- **When:** During the 4-step analysis pipeline (Step 3)
- **Why:** CBT-trained analysis to identify cognitive distortions, recurring themes, sentiment trends, and growth areas
- **Returns:** JSON with cognitive_distortions, recurring_themes, sentiment_trend, growth_areas

### 5. `generate_artwork_prompt`
- **Where:** Entry form - "Finish Entry" flow
- **When:** During the 4-step analysis pipeline (Step 4)
- **Why:** Creates abstract art prompts from detected themes/emotions (NOT from raw content for privacy)
- **Returns:** Stable Diffusion prompt text

### 6. `generate_deeper_questions`
- **Where:** Entry form - "Go Deeper" feature
- **When:** User clicks "Go Deeper" button during writing
- **Why:** Generates 3-5 reflective follow-up questions to help explore emotions and patterns
- **Returns:** JSON array of question strings

### 7. `tag_extraction`
- **Where:** Entry form - Automatic tag generation
- **When:** After entry is saved (background process)
- **Why:** Extracts 3-7 relevant German tags from content (themes, emotions, activities, relationships)
- **Returns:** JSON array of tag strings

### 8. `suggest_title`
- **Where:** Entry view page - Quick title suggestion
- **When:** User wants a quick title without full analysis
- **Why:** Fast title generation (max 8 words) for entries
- **Returns:** Single title string

---

## 🏠 Dashboard (Homepage)
**Location:** `dashboard.html`  
**Purpose:** Personalized prompts and daily engagement

### 9. `daily_reflection_question`
- **Where:** Dashboard - "Daily Reflection" card
- **When:** Page loads, generates fresh question daily
- **Why:** Creates one personalized reflection question based on recent entries to encourage daily journaling
- **Returns:** Single question text

### 10. `generate_personalized_prompts`
- **Where:** Dashboard - "Suggestions" section
- **When:** Dashboard loads or user clicks "New Question"
- **Why:** Generates 3 personalized prompts: under-explored topic, revisit theme, growth opportunity
- **Returns:** JSON array with category, text, and reason for each prompt

### 11. `generate_personalized_prompts_embeddings`
- **Where:** Dashboard - "Suggestions" section (alternative method)
- **When:** Dashboard loads with embedding-based context
- **Why:** Alternative prompt generation using vector similarity instead of statistical analysis
- **Returns:** JSON array with category, text, and reason for each prompt

---

## 📊 Insights Page (Analytics)
**Location:** `insights.html`  
**Purpose:** Cross-entry pattern analysis and personality insights

### 12. `generate_big_five_analysis`
- **Where:** Insights - Personality section
- **When:** User views personality insights across multiple entries
- **Why:** Analyzes journal excerpts to provide Big Five personality insights (openness, conscientiousness, extraversion, agreeableness, neuroticism)
- **Returns:** JSON with personality dimension summaries and evidence

### 13. `generate_recurring_topics`
- **Where:** Insights - Recurring topics section
- **When:** User views recurring topics with AI-generated insights
- **Why:** Summarizes each recurring topic into a short, supportive insight
- **Returns:** JSON array of topic titles with insights

---

## 💬 Chat Feature
**Location:** `app.py` - `/api/chat` endpoint  
**Purpose:** Conversational AI assistant with different contexts

### 14. `chat_persona_entry`
- **Where:** Entry view - AI chat sidebar
- **When:** User chats about a specific journal entry
- **Why:** Sets AI persona as "compassionate therapist" for entry-specific reflection
- **Returns:** System prompt text (not directly visible to user)

### 15. `chat_persona_global`
- **Where:** Global chat or insights chat
- **When:** User asks questions across multiple entries or general patterns
- **Why:** Sets AI persona as "data analyst" for cross-entry pattern analysis
- **Returns:** System prompt text (not directly visible to user)

---

## 🎨 Image Generation
**Location:** `app.py` - `/api/generate/image` endpoint  
**Purpose:** Direct image generation from entry content

### 16. `generate_image_prompt`
- **Where:** Entry view - "Generate Image" feature
- **When:** User wants to generate artwork directly from entry content
- **Why:** Creates Stable Diffusion prompt from entry content (can include personal details)
- **Returns:** SD prompt text
- **Note:** Different from `generate_artwork_prompt` which uses abstract themes only

---

## 🔍 Unused/Orphaned Prompts

### 17. `emotion_summary`
- **Where:** No current usage found
- **Purpose:** Was designed to summarize why user feels a specific emotion
- **Status:** Appears to be legacy/unused

### 18. `image_generation`
- **Where:** No current usage found
- **Purpose:** Abstract art description (max 50 words)
- **Status:** Appears to be duplicate of `generate_artwork_prompt`

---

## Summary by Location

| Location | Prompts Count | Prompts |
|----------|--------------|---------|
| **Journal Entry** | 8 | analyze_entry, generate_summary_and_title, detect_emotions, identify_patterns, generate_artwork_prompt, generate_deeper_questions, tag_extraction, suggest_title |
| **Dashboard** | 3 | daily_reflection_question, generate_personalized_prompts, generate_personalized_prompts_embeddings |
| **Insights** | 2 | generate_big_five_analysis, generate_recurring_topics |
| **Chat** | 2 | chat_persona_entry, chat_persona_global |
| **Image Gen** | 1 | generate_image_prompt |
| **Unused** | 2 | emotion_summary, image_generation |

---

## Usage Frequency

### High Frequency (Used on every entry):
- `generate_summary_and_title`
- `detect_emotions`
- `tag_extraction`
- `generate_artwork_prompt`

### Medium Frequency (User-triggered):
- `analyze_entry`
- `generate_deeper_questions`
- `suggest_title`
- `daily_reflection_question`
- `generate_personalized_prompts`

### Low Frequency (Analytics/Chat):
- `identify_patterns`
- `generate_big_five_analysis`
- `generate_recurring_topics`
- `chat_persona_entry`
- `chat_persona_global`

### Rare/Unused:
- `generate_image_prompt` (direct generation)
- `generate_personalized_prompts_embeddings` (alternative method)
- `emotion_summary`
- `image_generation`
