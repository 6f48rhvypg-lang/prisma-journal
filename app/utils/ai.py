import logging
import re
import time
import requests
from config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default System Prompts (fallback if DB unavailable)
# ---------------------------------------------------------------------------

_DEFAULT_PROMPTS = {
    "analyze_entry": (
        "You are an empathetic journaling coach. Analyze the journal entry and provide:\n"
        "1. **Emotional Tone** - The primary emotions expressed\n"
        "2. **Key Themes** - Main topics or concerns\n"
        "3. **Cognitive Patterns** - Any thinking patterns (positive or limiting)\n"
        "4. **Reframe** - A constructive reframe of any negative thoughts\n"
        "5. **Follow-up Prompt** - One thought-provoking question to go deeper\n\n"
        "Keep your response concise and supportive.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "suggest_title": (
        "Generate a short, evocative title (max 8 words) for this journal entry. "
        "Return only the title, no quotes or extra text.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_image_prompt": (
        "Based on this journal entry, create a short Stable Diffusion image prompt "
        "(max 50 words) that captures the mood and theme as {style} art. "
        "Return only the prompt.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_deeper_questions": (
        "You are a thoughtful journaling coach. Generate an insightful follow-up question that:\n"
        "1. Helps explore emotions more deeply\n"
        "2. Identifies underlying motivations or patterns\n"
        "3. Considers different perspectives\n"
        "4. Is open-ended, not yes/no\n"
        "5. Feels supportive, not interrogative\n\n"
        "Return ONE question only. No preface, no list.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_deeper_questions_followup": (
        "You are a thoughtful journaling coach. The user already received these questions:\n"
        "{previous_questions}\n\n"
        "Generate ONE new follow-up question that is VERY DIFFERENT in angle, wording, and focus from all previous questions.\n"
        "Do not repeat topics already covered. Be fresh, specific, and open-ended.\n\n"
        "Return ONE question only. No preface, no list.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_summary_and_title": (
        "# Rolle und Ziel\n"
        "Du bist ein erfahrener Analytiker mit einem besonderen Talent f\u00fcr Textanalyse und Zusammenfassung. "
        "Dein Ziel ist es, den folgenden Tagebucheintrag zu analysieren und eine strukturierte \u00dcbersicht zu erstellen.\n\n"
        "# Anweisungen\n"
        "1.  Analysiere den Tagebucheintrag gr\u00fcndlich.\n"
        "2.  Erstelle auf Basis dieser Analyse ein JSON-Objekt mit den folgenden drei Feldern:\n"
        "    - \"title\": Ein kurzer, aussagekr\u00e4ftiger Titel (max. 8 W\u00f6rter), der das zentrale Thema einf\u00e4ngt.\n"
        "    - \"summary\": Eine kurze Zusammenfassung in 2-3 S\u00e4tzen, die die wichtigsten Punkte wiedergibt.\n"
        "    - \"themes\": Ein Array mit 2-5 zentralen Themen oder Stichw\u00f6rtern, die im Eintrag behandelt werden.\n\n"
        "# Ausgabeformat\n"
        "Gib ausschlie\u00dflich ein valides JSON-Objekt aus, ohne jegliche Zus\u00e4tze, Kommentare oder Markdown-Formatierung. "
        "Das JSON muss genau diese Struktur haben: {\"title\": \"...\", \"summary\": \"...\", \"themes\": [\"...\", \"...\"]}\n\n"
        "# Wichtig\n"
        "Alle Texte (Titel, Zusammenfassung, Themen) müssen auf Deutsch verfasst sein.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "detect_emotions": (
        "You are an emotion analyst using Plutchik's wheel. Analyze this journal entry for emotions.\n"
        "Valid emotions: {emotions_list}\n\n"
        "Return a JSON object with:\n"
        '- "emotions": Array of detected emotions, each with:\n'
        '  - "emotion": one of the valid emotions\n'
        '  - "intensity": "low", "medium", or "high"\n'
        '  - "frequency": 0.0-1.0 (how prominent in the text)\n'
        '  - "passage": a short quote from the text showing this emotion\n\n'
        "Only include emotions actually present. Return ONLY valid JSON."
    ),
    "identify_patterns": (
        "You are a CBT-trained cognitive analyst. Analyze this journal entry for thinking patterns.\n"
        "{themes_hint}"
        "Return a JSON object with:\n"
        '- "cognitive_distortions": Array of any cognitive distortions found, each with:\n'
        '  - "type": name of distortion (e.g., "all-or-nothing thinking", "catastrophizing", "mind reading")\n'
        '  - "example": quote from text showing this pattern\n'
        '  - "reframe": a healthier alternative perspective\n'
        '- "recurring_themes": Array of themes that might recur in their journaling\n'
        '- "sentiment_trend": "positive", "negative", "mixed", or "neutral"\n'
        '- "growth_areas": Array of 1-3 areas for personal growth or reflection\n\n'
        "Be supportive, not critical. Return ONLY valid JSON.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_artwork_prompt": (
        "Create a Stable Diffusion prompt (max 50 words) for abstract {style} art.\n"
        "The artwork should capture the mood and themes below WITHOUT including any specific personal details.\n"
        "Focus on colors, shapes, textures, and abstract representations.\n"
        "Return ONLY the prompt text, nothing else.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_personalized_prompts": (
        "You are a thoughtful journaling coach. Based on this user's journal history, "
        "generate 3 personalized writing prompts that:\n"
        "1. One prompt to explore an UNDER-EXPLORED topic they haven't written much about\n"
        "2. One prompt to REVISIT a theme from their past with fresh perspective\n"
        "3. One prompt for GROWTH based on patterns you notice\n\n"
        "Return ONLY a JSON array of 3 objects, each with:\n"
        '- "category": "explore", "revisit", or "growth"\n'
        '- "text": the prompt text (open-ended question)\n'
        '- "reason": brief explanation why this prompt is suggested (1 sentence)\n\n'
        "Return ONLY valid JSON, no other text.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_personalized_prompts_embeddings": (
        "You are a thoughtful journaling coach. Generate 3 prompts based on this context:\n"
        "1) Explore an under-explored topic\n"
        "2) Revisit a theme from months ago\n"
        "3) Encourage growth based on patterns you infer\n\n"
        "Return ONLY a JSON array of 3 objects, each with:\n"
        '- "category": "explore", "revisit", or "growth"\n'
        '- "text": an open-ended question\n'
        '- "reason": a brief one-sentence rationale\n\n'
        "Return ONLY valid JSON, no other text.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_big_five_analysis": (
        "You are a personality analyst. Based on the journal excerpts, provide Big Five insights.\n"
        "Return ONLY a JSON object with keys: openness, conscientiousness, extraversion, agreeableness, neuroticism.\n"
        "Each key should map to an object with:\n"
        '- "summary": 2-3 sentences of insight\n'
        '- "evidence": array of 2-3 short evidence phrases from the excerpts\n\n'
        "Timeframe: {timeframe_label}. Avoid clinical language.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "generate_recurring_topics": (
        "You are a journaling insights assistant. Summarize each topic into a short insight.\n"
        "Return ONLY a JSON array of objects with keys:\n"
        '- "title": short topic title\n'
        '- "insight": 2-3 sentence insight\n\n'
        "Keep the tone supportive and concise.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "daily_reflection_question": (
        "You are a thoughtful journaling coach. Based on the user's recent journal entries, "
        "generate ONE personalized daily reflection question.\n\n"
        "The question should:\n"
        "1. Connect to themes or emotions from their recent writing\n"
        "2. Be open-ended and thought-provoking\n"
        "3. Encourage deeper self-reflection\n"
        "4. Feel fresh and not repetitive\n\n"
        "IMPORTANT: Always respond in German.\n\n"
        "Return ONLY the question text, nothing else.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "chat_persona_entry": (
        "You are a compassionate therapist helping the user reflect on a single journal entry.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "chat_persona_global": (
        "You are a data analyst summarizing patterns across multiple journal entries.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
    "tag_extraction": (
        "Du bist ein Tagging-System für deutsche Tagebucheinträge. Extrahiere EXAKT 5 relevante Tags.\n\n"
        "ANFORDERUNGEN (streng befolgen):\n"
        "1. Genau 5 Tags im JSON-Array\n"
        "2. NUR Kleinbuchstaben\n"
        "3. Bindestriche für zusammengesetzte Begriffe: \"arbeit-stress\", \"familienessen\"\n"
        "4. Maximale Länge: 20 Zeichen pro Tag\n"
        "5. KEINE Artikel, Konjunktionen oder Zeitangaben\n"
        "6. KEINE der Wörter: der, und, tag, zeit, ding, fühlen, gefühlt, heute, denken, gestern\n\n"
        "KATEGORIEN (mindestens eine aus jeder relevanten Kategorie wählen):\n"
        "- Thema: arbeit, familie, gesundheit, projekt, hobby\n"
        "- Emotion: freude, angst, frustration, dankbarkeit, stress\n"
        "- Ort: zuhause, arbeitsplatz, unterwegs, urlaub\n"
        "- Beziehung: partner, freund, kollege, familie\n"
        "- Aktivität: meeting, spaziergang, kochen, lesen\n\n"
        "OUTPUT-FORMAT (streng):\n"
        '[\"tag1\", \"tag2\", \"tag3\", \"tag4\", \"tag5\"]\n\n'
        "Eintrag:\n{content}\n\n"
        "WICHTIG: Antworte AUSSCHLIEßLICH auf Deutsch. "
        "NUR das JSON-Array, keine Erklärungen, kein Markdown."
    ),
    "identify_baustellen": (
        "Analysiere die Tagebucheinträge des Nutzers und identifiziere 3-5 aktive 'Baustellen' "
        "(ungelöste Probleme, laufende Anliegen, Themen, die den Nutzer aktuell beschäftigen).\n\n"
        "Eine Baustelle ist ein Thema, das:\n"
        "- Ungelöst oder unvollständig ist\n"
        "- Mehrfach in den Einträgen vorkommt oder intensiv behandelt wurde\n"
        "- Aktuell relevant ist (nicht nur historisch)\n"
        "- Emotional besetzt oder handlungsrelevant ist\n\n"
        "Für jede Baustelle gib zurück:\n"
        '- "headline": Ultra-kurzer, präziser Titel (2-4 Wörter, knackig und klar, keine Sätze)\n'
        '- "core_problem": 1-2 Sätze, die das Kernproblem beschreiben\n'
        '- "recent_development": Was hat sich kürzlich entwickelt oder verändert\n'
        '- "status": Einer von: "escalating" (verschärft sich), "stable" (besteht fort), "improving" (bessert sich), "dormant" (schlummert)\n'
        '- "urgency": Zahl 1-5 (5 = braucht sofort Aufmerksamkeit, 1 = kann warten)\n'
        '- "entry_count": Wie viele Einträge beziehen sich auf dieses Thema (Schätzung)\n'
        '- "last_mentioned": Datum des neuesten Eintrags zu diesem Thema (ISO-Format)\n\n'
        "Fokus auf: ungelöste Konflikte, laufende Stressfaktoren, wiederkehrende Sorgen, "
        "unfertige Projekte, aktive Lebens-Herausforderungen, Beziehungsspannungen.\n\n"
        "Gib NUR ein valides JSON-Array zurück. Kein Markdown, keine Erklärung.\n\n"
        "WICHTIG: Antworte AUSSCHLIESSLICH auf Deutsch. "
        "Verwende KEINE anderen Sprachen wie Englisch oder Chinesisch. "
        "Alle Texte müssen auf Deutsch verfasst sein."
    ),
}


def _get_prompt(key, **kwargs):
    """Get a system prompt from database with fallback to defaults.

    Args:
        key: The prompt key (e.g., 'analyze_entry')
        **kwargs: Format arguments to substitute into the prompt

    Returns:
        The prompt text with any {placeholders} substituted
    """
    try:
        from database.db import get_system_prompt
        prompt = get_system_prompt(key, default=_DEFAULT_PROMPTS.get(key, ""))
    except Exception as e:
        log.warning("Failed to load prompt '%s' from DB: %s", key, e)
        prompt = _DEFAULT_PROMPTS.get(key, "")

    # Apply any format arguments if provided
    if kwargs and prompt:
        try:
            prompt = prompt.format(**kwargs)
        except KeyError:
            # Prompt may have placeholders that aren't being filled yet
            pass

    return prompt


def _check_llm_available():
    """Check if the configured LLM provider is available. Returns (is_available, error_message)."""
    from utils.services import status
    
    if Config.LLM_PROVIDER == "lmstudio":
        if not status.lmstudio:
            return False, f"LM Studio is not available. {status.lmstudio_message}"
    else:  # Default to Ollama
        if not status.ollama:
            return False, f"Ollama is not available. {status.ollama_message}"
    
    return True, ""


# ---------------------------------------------------------------------------
# Retry and Error Handling Configuration
# ---------------------------------------------------------------------------

# Exceptions that are worth retrying
RETRYABLE_EXCEPTIONS = (
    requests.ConnectionError,
    requests.Timeout,
)

# Maximum retries for transient failures
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds


def _should_retry(exception):
    """Determine if an exception is worth retrying."""
    if isinstance(exception, requests.HTTPError):
        # Retry 5xx errors and 429 (rate limit)
        if exception.response is not None:
            return exception.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exception, RETRYABLE_EXCEPTIONS)


def _make_ollama_request(url, payload, timeout):
    """Make a single request to Ollama API with error handling."""
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", ""), None
    except requests.ConnectionError:
        return None, (
            "[Error: Cannot connect to Ollama at "
            f"{Config.OLLAMA_BASE_URL}. Make sure it is running "
            "(ollama serve).]"
        )
    except requests.Timeout:
        return None, (
            f"[Error: Ollama request timed out after {timeout}s. "
            "Try a smaller model or increase OLLAMA_TIMEOUT.]"
        )
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None, (
                f"[Error: Model '{payload.get('model', 'unknown')}' not found in Ollama. "
                f"Run: ollama pull {payload.get('model', 'unknown')}]"
            )
        return None, f"[Error: Ollama returned HTTP {e.response.status_code if e.response else '?'}]"
    except Exception as e:
        return None, f"[Error: {e}]"


def _make_lmstudio_request(url, payload, timeout):
    """Make a single request to LM Studio (OpenAI-compatible) API with error handling."""
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Extract content from OpenAI format: choices[0].message.content
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {}).get("content", ""), None
        return "", None
    except requests.ConnectionError:
        return None, (
            "[Error: Cannot connect to LM Studio at "
            f"{Config.LMSTUDIO_BASE_URL}. Make sure it is running "
            "with the local server enabled.]"
        )
    except requests.Timeout:
        return None, (
            f"[Error: LM Studio request timed out after {timeout}s. "
            "Try a smaller model or increase LMSTUDIO_TIMEOUT.]"
        )
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None, (
                f"[Error: Model '{payload.get('model', 'unknown')}' not found in LM Studio. "
                "Load a model in LM Studio.]"
            )
        return None, f"[Error: LM Studio returned HTTP {e.response.status_code if e.response else '?'}]"
    except Exception as e:
        return None, f"[Error: {e}]"


def chat_with_ollama(prompt, system_prompt=None, model=None, retry=True, timeout=None) -> str:
    """Send a prompt to the configured LLM provider (Ollama or LM Studio) and return the response text.

    Includes retry logic for transient failures with exponential backoff.

    Args:
        prompt: The prompt to send
        system_prompt: Optional system prompt
        model: Optional model override (defaults to configured model)
        retry: Whether to retry on transient failures (default True)
        timeout: Optional timeout override (defaults to configured timeout)

    Returns:
        Response text on success, or error message string starting with "[Error"
    """
    # Route to the appropriate provider based on config
    if Config.LLM_PROVIDER == "lmstudio":
        response = _chat_with_lmstudio(prompt, system_prompt, model, retry, timeout)
    else:
        response = _chat_with_ollama(prompt, system_prompt, model, retry, timeout)

    if isinstance(response, str):
        return response
    return "[Error: Empty response from LLM provider.]"


def _chat_with_ollama(prompt, system_prompt=None, model=None, retry=True, timeout=None) -> str:
    """Internal function for Ollama API calls."""
    from utils.services import status

    if not status.ollama:
        return (
            "[Ollama is not available. " + status.ollama_message + "]"
        )

    model = model or Config.OLLAMA_MODEL
    timeout = timeout or Config.OLLAMA_TIMEOUT
    url = f"{Config.OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    max_attempts = MAX_RETRIES + 1 if retry else 1
    last_error = None

    for attempt in range(max_attempts):
        start_time = time.time()
        result, error = _make_ollama_request(url, payload, timeout)

        if result is not None:
            duration = time.time() - start_time
            log.debug("Ollama request completed in %.1fs (attempt %d)", duration, attempt + 1)
            return result

        last_error = error

        # Don't retry connection errors that indicate Ollama isn't running
        if error and "[Error: Cannot connect" in error:
            break

        # Don't retry 404 (model not found)
        if error and "not found in Ollama" in error:
            break

        # Retry with backoff for other errors
        if attempt < max_attempts - 1:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(
                "Ollama request failed (attempt %d/%d): %s. Retrying in %.1fs",
                attempt + 1, max_attempts, error, delay
            )
            time.sleep(delay)

    log.error("Ollama request failed after %d attempts: %s", max_attempts, last_error)
    return last_error or "[Error: Unknown Ollama error.]"


def _chat_with_lmstudio(prompt, system_prompt=None, model=None, retry=True, timeout=None) -> str:
    """Internal function for LM Studio (OpenAI-compatible) API calls."""
    from utils.services import status

    if not status.lmstudio:
        return (
            "[LM Studio is not available. " + status.lmstudio_message + "]"
        )

    model = model or Config.LMSTUDIO_MODEL
    timeout = timeout or Config.LMSTUDIO_TIMEOUT
    url = f"{Config.LMSTUDIO_BASE_URL}/chat/completions"

    # Build messages in OpenAI format
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }

    max_attempts = MAX_RETRIES + 1 if retry else 1
    last_error = None

    for attempt in range(max_attempts):
        start_time = time.time()
        result, error = _make_lmstudio_request(url, payload, timeout)

        if result is not None:
            duration = time.time() - start_time
            log.debug("LM Studio request completed in %.1fs (attempt %d)", duration, attempt + 1)
            return result

        last_error = error

        # Don't retry connection errors
        if error and "[Error: Cannot connect" in error:
            break

        # Don't retry 404 (model not found)
        if error and "not found in LM Studio" in error:
            break

        # Retry with backoff for other errors
        if attempt < max_attempts - 1:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(
                "LM Studio request failed (attempt %d/%d): %s. Retrying in %.1fs",
                attempt + 1, max_attempts, error, delay
            )
            time.sleep(delay)

    log.error("LM Studio request failed after %d attempts: %s", max_attempts, last_error)
    return last_error or "[Error: Unknown LM Studio error.]"


def analyze_entry(content):
    """Analyze a journal entry and return AI insights."""
    system = _get_prompt("analyze_entry")
    return chat_with_ollama(content, system_prompt=system)


def suggest_title(content):
    """Suggest a short title for a journal entry."""
    system = _get_prompt("suggest_title")
    return chat_with_ollama(content[:500], system_prompt=system)


def generate_image_prompt(content):
    """Generate a Stable Diffusion prompt from journal entry content."""
    style = Config.SD_DEFAULT_STYLE
    system = _get_prompt("generate_image_prompt", style=style)
    return chat_with_ollama(content[:500], system_prompt=system)


def generate_deeper_questions(text, previous_questions=None):
    """Generate a reflective follow-up question for a journal entry."""
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not text or len(text.strip()) < 20:
        return {"error": "Entry is too short to generate meaningful questions."}

    previous_questions = previous_questions or []
    cleaned_previous = [q.strip() for q in previous_questions if isinstance(q, str) and q.strip()]
    formatted_previous = "\n".join(f"- {q}" for q in cleaned_previous)
    if not formatted_previous:
        formatted_previous = "(none)"

    prompt_key = "generate_deeper_questions_followup" if cleaned_previous else "generate_deeper_questions"
    inline_previous = " | ".join(cleaned_previous)
    system = _get_prompt(
        prompt_key,
        previous_questions=formatted_previous,
        previous_questions_inline=inline_previous,
    )

    prompt_parts = [f'The user has written:\n"""\n{text[:2000]}\n"""']

    if cleaned_previous:
        prev_list = "\n".join(f"- {q}" for q in cleaned_previous[-10:])
        prompt_parts.append(f"\nPrevious questions:\n{prev_list}")

    prompt_parts.append("\nGenerate ONE new insightful follow-up question. Return only the question text:")

    response = chat_with_ollama("\n".join(prompt_parts), system_prompt=system)

    # Check for error
    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    # Log the raw response for debugging
    log.debug("Deeper questions raw response: %s", response[:500])

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
        cleaned = cleaned.strip()

    question = None
    if cleaned.startswith("["):
        questions, error = _parse_json_response(response, expected_type="array")
        if not error and isinstance(questions, list):
            for q in questions:
                if isinstance(q, str) and q.strip():
                    question = q.strip()
                    break
    elif cleaned.startswith("{"):
        payload, error = _parse_json_response(response, expected_type="object")
        if not error and isinstance(payload, dict):
            q = payload.get("question")
            if isinstance(q, str) and q.strip():
                question = q.strip()

    if not question and cleaned:
        question = cleaned

    if question:
        return {"question": question}

    log.warning("Could not parse question. Raw response: %s", response[:500])
    return {"error": "Could not parse question from AI response."}


# ---------------------------------------------------------------------------
# JSON Parsing Helper
# ---------------------------------------------------------------------------

def _parse_json_response(response: str, expected_type="object"):
    """Parse JSON from AI response, handling common formatting issues.

    Args:
        response: The AI response string
        expected_type: "object" for {} or "array" for []

    Returns:
        tuple: (parsed_data, error_message)
        If successful, error_message is None
        If failed, parsed_data is None
    """
    import json
    import re

    # Check for error responses
    if response.startswith("[Error") or response.startswith("[Ollama"):
        return None, response

    if not response or not response.strip():
        return None, "Empty response from AI"

    # Strip markdown code blocks if present
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove opening code block (```json or ```)
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        # Remove closing code block
        cleaned = re.sub(r'\n?```$', '', cleaned)
        cleaned = cleaned.strip()

    # Find the JSON content
    if expected_type == "array":
        start_char, end_char = "[", "]"
    else:
        start_char, end_char = "{", "}"

    start = cleaned.find(start_char)
    end = cleaned.rfind(end_char) + 1

    if start < 0 or end <= start:
        log.warning("AI response missing JSON %s: %s", expected_type, response[:500])
        return None, f"AI response did not contain valid JSON {expected_type}"

    json_str = cleaned[start:end]

    try:
        data = json.loads(json_str)
        return data, None
    except json.JSONDecodeError as e:
        log.warning("JSON parse error: %s. Response: %s", e, json_str[:500])
        return None, f"AI returned invalid JSON: {str(e)}"


# ---------------------------------------------------------------------------
# Comprehensive Entry Analysis Functions
# ---------------------------------------------------------------------------

PLUTCHIK_EMOTIONS = [
    "joy", "trust", "fear", "surprise",
    "sadness", "disgust", "anger", "anticipation"
]


def generate_summary_and_title(content):
    """Generate a summary and title for a journal entry.

    Returns:
        dict with keys: summary, title, themes
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not content or len(content.strip()) < 10:
        return {"error": "Entry content is too short for analysis."}

    system = _get_prompt("generate_summary_and_title")

    response = chat_with_ollama(content[:3000], system_prompt=system)

    data, error = _parse_json_response(response, "object")
    if error:
        return {"error": error}
    if not isinstance(data, dict):
        return {"error": "AI returned unexpected JSON format (expected object)."}

    return {
        "title": data.get("title", "Untitled Entry"),
        "summary": data.get("summary", ""),
        "themes": data.get("themes", []),
    }


def detect_emotions(content):
    """Detect Plutchik emotions in a journal entry.

    Returns:
        dict with key: emotions (list of {emotion, intensity, frequency, passages})
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not content or len(content.strip()) < 10:
        return {"error": "Entry content is too short for emotion analysis."}

    emotions_list = ", ".join(PLUTCHIK_EMOTIONS)
    system = _get_prompt("detect_emotions", emotions_list=emotions_list)

    response = chat_with_ollama(content[:3000], system_prompt=system)

    data, error = _parse_json_response(response, "object")
    if error:
        return {"error": error}
    if not isinstance(data, dict):
        return {"error": "AI returned unexpected JSON format (expected object)."}

    emotions = data.get("emotions", [])
    # Validate and clean emotions
    valid_emotions = []
    for em in emotions:
        if isinstance(em, dict) and em.get("emotion") in PLUTCHIK_EMOTIONS:
            try:
                freq = min(1.0, max(0.0, float(em.get("frequency", 0.5))))
            except (ValueError, TypeError):
                freq = 0.5
            valid_emotions.append({
                "emotion": em["emotion"],
                "intensity": em.get("intensity", "medium"),
                "frequency": freq,
                "passage": em.get("passage", ""),
            })

    if not valid_emotions:
        log.warning("No valid emotions detected in entry")

    return {"emotions": valid_emotions}


def identify_patterns(content, themes=None):
    """Identify cognitive patterns and distortions in a journal entry.

    Args:
        content: The journal entry text
        themes: Optional list of themes from the summary step

    Returns:
        dict with keys: cognitive_distortions, recurring_themes, sentiment_trend, growth_areas
        or dict with key: error
    """
    import json

    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    themes_hint = ""
    if themes:
        themes_hint = f"\nIdentified themes: {', '.join(themes)}\n"

    system = _get_prompt("identify_patterns", themes_hint=themes_hint)

    response = chat_with_ollama(content[:3000], system_prompt=system)

    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            return {
                "cognitive_distortions": data.get("cognitive_distortions", []),
                "recurring_themes": data.get("recurring_themes", []),
                "sentiment_trend": data.get("sentiment_trend", "neutral"),
                "growth_areas": data.get("growth_areas", []),
            }
        return {"error": "Could not parse patterns from AI response."}
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON for patterns."}


def generate_artwork_prompt_for_analysis(themes, emotions, sentiment):
    """Generate an abstract artwork prompt based on analysis results.

    This does NOT include specific entry content for privacy - only the
    abstract themes and emotions detected.

    Returns:
        dict with key: artwork_prompt
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    style = Config.SD_DEFAULT_STYLE

    # Build context from analysis
    emotion_names = [e["emotion"] for e in emotions[:3]] if emotions else ["calm"]
    theme_list = themes[:3] if themes else ["reflection"]

    prompt_context = (
        f"Themes: {', '.join(theme_list)}\n"
        f"Emotions: {', '.join(emotion_names)}\n"
        f"Overall sentiment: {sentiment}\n"
    )

    system = _get_prompt("generate_artwork_prompt", style=style)

    response = chat_with_ollama(prompt_context, system_prompt=system)

    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    # Clean up the response
    prompt = response.strip().strip('"\'')
    return {"artwork_prompt": prompt}


def generate_personalized_prompts(themes_history, emotions_history, recent_topics, entry_count=0):
    """Generate personalized journal prompts based on user's history.

    Args:
        themes_history: List of themes from past entries (most common first)
        emotions_history: List of emotions from past entries with counts
        recent_topics: List of topics from recent entries
        entry_count: Total number of entries

    Returns:
        dict with keys: prompts (list of {category, text, reason})
        or dict with key: error
    """
    import json
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if entry_count < 3:
        return {"error": "Not enough journal history to generate personalized prompts. Minimum 3 entries required."}

    # Build context
    themes_str = ", ".join(themes_history[:10]) if themes_history else "general reflection"
    emotions_str = ", ".join([f"{e['emotion']} ({e['count']})" for e in emotions_history[:5]]) if emotions_history else "mixed"
    recent_str = ", ".join(recent_topics[:5]) if recent_topics else "various"

    context = (
        f"User's journal history:\n"
        f"- Total entries: {entry_count}\n"
        f"- Common themes: {themes_str}\n"
        f"- Frequent emotions: {emotions_str}\n"
        f"- Recent topics: {recent_str}\n"
    )

    system = _get_prompt("generate_personalized_prompts")

    response = chat_with_ollama(context, system_prompt=system)

    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            prompts = json.loads(response[start:end])
            if isinstance(prompts, list):
                valid_prompts = []
                for p in prompts:
                    if isinstance(p, dict) and "text" in p:
                        valid_prompts.append({
                            "category": p.get("category", "reflection"),
                            "text": p.get("text", ""),
                            "reason": p.get("reason", ""),
                        })
                if valid_prompts:
                    return {"prompts": valid_prompts}
        return {"error": "Could not parse prompts from AI response."}
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON for prompts."}


def generate_personalized_prompts_from_embeddings(
    under_explored_topics,
    revisit_topics,
    recent_topics,
    entry_count=0,
):
    """Generate personalized prompts using embedding-derived topic signals.

    Args:
        under_explored_topics: List of brief topic labels to explore
        revisit_topics: List of older themes to revisit
        recent_topics: List of recent topics for context
        entry_count: Total number of entries
    """
    import json

    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if entry_count < 3:
        return {"error": "Not enough journal history to generate personalized prompts. Minimum 3 entries required."}

    under_str = ", ".join(under_explored_topics[:5]) if under_explored_topics else "new areas"
    revisit_str = ", ".join(revisit_topics[:5]) if revisit_topics else "earlier themes"
    recent_str = ", ".join(recent_topics[:5]) if recent_topics else "recent reflections"

    context = (
        f"User journal context (embedding analysis):\n"
        f"- Total entries: {entry_count}\n"
        f"- Under-explored topics: {under_str}\n"
        f"- Themes to revisit (months ago): {revisit_str}\n"
        f"- Recent topics: {recent_str}\n"
    )

    system = _get_prompt("generate_personalized_prompts_embeddings")

    response = chat_with_ollama(context, system_prompt=system)

    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            prompts = json.loads(response[start:end])
            if isinstance(prompts, list):
                valid_prompts = []
                for p in prompts:
                    if isinstance(p, dict) and "text" in p:
                        valid_prompts.append({
                            "category": p.get("category", "reflection"),
                            "text": p.get("text", ""),
                            "reason": p.get("reason", ""),
                        })
                if valid_prompts:
                    return {"prompts": valid_prompts}
        return {"error": "Could not parse prompts from AI response."}
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON for prompts."}


def generate_big_five_analysis(entry_summaries, timeframe_label):
    """Generate Big Five personality insights from journal summaries.

    Args:
        entry_summaries: list of strings with entry summaries or excerpts
        timeframe_label: string label for the timeframe (e.g., "Last week")

    Returns:
        dict with keys: openness, conscientiousness, extraversion, agreeableness, neuroticism
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not entry_summaries:
        return {"error": "Not enough journal data for personality analysis."}

    context = "\n".join(f"- {line}" for line in entry_summaries[:30])

    system = _get_prompt("generate_big_five_analysis", timeframe_label=timeframe_label)

    response = chat_with_ollama(context, system_prompt=system)
    data, error = _parse_json_response(response, "object")
    if error:
        return {"error": error}
    if not isinstance(data, dict):
        return {"error": "AI returned unexpected JSON format (expected object)."}

    return {
        "openness": data.get("openness", {}),
        "conscientiousness": data.get("conscientiousness", {}),
        "extraversion": data.get("extraversion", {}),
        "agreeableness": data.get("agreeableness", {}),
        "neuroticism": data.get("neuroticism", {}),
    }


def generate_recurring_topics(topic_inputs):
    """Generate short insights for recurring topics.

    Args:
        topic_inputs: list of dicts with keys: topic, examples (list of snippets)

    Returns:
        dict with key: topics (list of {title, insight})
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not topic_inputs:
        return {"error": "No topics available."}

    formatted = []
    for item in topic_inputs[:6]:
        topic = item.get("topic", "Topic")
        examples = item.get("examples", [])[:3]
        formatted.append(f"Topic: {topic}\nExamples:\n" + "\n".join(f"- {ex}" for ex in examples))

    system = _get_prompt("generate_recurring_topics")

    response = chat_with_ollama("\n\n".join(formatted), system_prompt=system)
    data, error = _parse_json_response(response, "array")
    if error:
        return {"error": error}
    if not isinstance(data, list):
        return {"error": "AI returned unexpected JSON format (expected array)."}

    topics = []
    for item in data:
        if not isinstance(item, dict):
            continue
        topics.append({
            "title": item.get("title", "Untitled"),
            "insight": item.get("insight", ""),
        })
    return {"topics": topics}


def generate_baustellen_analysis(entry_data):
    """Generate Baustellen (ongoing concerns) analysis from journal entries.

    Args:
        entry_data: list of dicts with keys: id, date, content, tags, emotions

    Returns:
        dict with key: baustellen (list of Baustelle objects)
        or dict with key: error
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not entry_data:
        return {"error": "Not enough journal data for Baustellen analysis."}

    # Format entries for the AI
    formatted_entries = []
    for entry in entry_data[:50]:  # Limit to prevent token overflow
        date_str = entry.get("date", "Unknown date")
        content = entry.get("content", "")
        tags = entry.get("tags", [])
        emotions = entry.get("emotions", [])
        
        entry_str = f"Eintrag vom {date_str}:\n{content[:300]}"
        if tags:
            entry_str += f"\nTags: {', '.join(tags[:5])}"
        if emotions:
            entry_str += f"\nEmotionen: {', '.join(emotions[:3])}"
        formatted_entries.append(entry_str)

    system = _get_prompt("identify_baustellen")

    response = chat_with_ollama("\n\n---\n\n".join(formatted_entries), system_prompt=system)
    data, error = _parse_json_response(response, "array")
    if error:
        return {"error": error}
    if not isinstance(data, list):
        return {"error": "AI returned unexpected JSON format (expected array)."}

    baustellen = []
    for item in data:
        if not isinstance(item, dict):
            continue
        baustellen.append({
            "headline": item.get("headline", "Unbenannte Baustelle"),
            "core_problem": item.get("core_problem", ""),
            "recent_development": item.get("recent_development", ""),
            "status": item.get("status", "stable"),
            "urgency": item.get("urgency", 3),
            "entry_count": item.get("entry_count", 1),
            "last_mentioned": item.get("last_mentioned", ""),
        })
    
    return {"baustellen": baustellen}


def generate_daily_question(recent_summaries):
    """Generate a personalized daily reflection question from recent entries.

    Args:
        recent_summaries: List of summary strings from recent journal entries

    Returns:
        dict with key: question (string)
        or dict with key: error (string)
    """
    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not recent_summaries:
        return {"error": "No recent entries to generate a personalized question."}

    # Build context from recent summaries
    context = "Recent journal entries:\n" + "\n".join(
        f"- {summary}" for summary in recent_summaries[:10]
    )

    system = _get_prompt("daily_reflection_question")
    response = chat_with_ollama(context, system_prompt=system)

    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    # Clean up the response
    question = response.strip().strip('"\'')
    return {"question": question}


# ---------------------------------------------------------------------------
# Tag Suggestion Functions
# ---------------------------------------------------------------------------

def suggest_tags(content, max_tags=7):
    """Extract relevant tags from journal entry content using small model.

    Args:
        content: The journal entry text
        max_tags: Maximum number of tags to return (default 7)

    Returns:
        dict with keys:
            - "suggested_tags": list of tag strings
            - "confidence": float (0.0-1.0) based on content length/quality
            - "error": error message if AI unavailable
    """
    from config import Config

    llm_ok, llm_error = _check_llm_available()
    if not llm_ok:
        return {"error": f"[{llm_error}]"}

    if not content or len(content.strip()) < Config.TAG_MIN_LENGTH:
        return {
            "suggested_tags": [],
            "confidence": 0.0,
            "error": f"Content too short (min {Config.TAG_MIN_LENGTH} chars)"
        }

    # Truncate content to avoid overwhelming small model
    truncated = content[:2000] if len(content) > 2000 else content

    # Use dedicated tag model (usually smaller/faster)
    tag_model = Config.TAG_MODEL

    # Get the prompt from database (editable in settings) or fallback to default
    system_prompt = _get_prompt("tag_extraction")
    
    response = chat_with_ollama(
        truncated,
        system_prompt=system_prompt.format(content=truncated),
        model=tag_model,
        timeout=15  # Short timeout for fast response
    )

    print(f"[suggest_tags] Raw Ollama response (first 500 chars): {response[:500]}")

    # Check for errors
    if response.startswith("[Error") or response.startswith("[Ollama"):
        return {"error": response}

    # Parse JSON response
    import json
    import re

    def _normalize_tag(tag):
        if not isinstance(tag, str):
            return None
        clean = tag.lower().strip().replace(" ", "-")
        if not clean or len(clean) > 30:
            return None
        return clean

    def _extract_tags(text):
        array_match = re.search(r"\[[\s\S]*\]", text)
        if array_match:
            try:
                data = json.loads(array_match.group(0))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        object_match = re.search(r"\{[\s\S]*\}", text)
        if object_match:
            try:
                data = json.loads(object_match.group(0))
                if isinstance(data, dict):
                    for key in ("suggested_tags", "tags", "tag_list"):
                        value = data.get(key)
                        if isinstance(value, list):
                            return value
            except json.JSONDecodeError:
                pass

        cleaned = text.strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        if not cleaned:
            return []

        parts = re.split(r"[\n,]+", cleaned)
        return [p.strip() for p in parts if p.strip()]

    raw_tags = _extract_tags(response)
    print(f"[suggest_tags] Extracted raw_tags: {raw_tags}")
    if not raw_tags:
        return {"error": "No tags found in AI response"}

    clean_tags = []
    for tag in raw_tags:
        normalized = _normalize_tag(tag)
        if normalized:
            clean_tags.append(normalized)

    if not clean_tags:
        return {"error": "No valid tags extracted from AI response"}

    # Remove duplicates and limit
    seen = set()
    unique_tags = []
    for tag in clean_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
            if len(unique_tags) >= max_tags:
                break

    # Calculate confidence based on content quality
    word_count = len(content.split())
    confidence = min(1.0, word_count / 100)  # More words = higher confidence

    return {
        "suggested_tags": unique_tags,
        "confidence": round(confidence, 2)
    }
