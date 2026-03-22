import json
import logging
import re
import sys
import os
import argparse
from urllib.parse import urlparse

# Ensure project root is on the path so config can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Add ffmpeg to PATH if installed via winget (Windows)
def _add_ffmpeg_to_path():
    """Find and add ffmpeg to PATH if not already available."""
    import shutil
    if shutil.which("ffmpeg"):
        return  # Already in PATH

    # Common winget installation paths
    winget_base = os.path.expanduser("~/AppData/Local/Microsoft/WinGet/Packages")
    if os.path.isdir(winget_base):
        for pkg_dir in os.listdir(winget_base):
            if "FFmpeg" in pkg_dir:
                pkg_path = os.path.join(winget_base, pkg_dir)
                for root, dirs, files in os.walk(pkg_path):
                    if "ffmpeg.exe" in files or "ffmpeg" in files:
                        os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                        return

_add_ffmpeg_to_path()

import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, g
from flask_compress import Compress
from werkzeug.utils import secure_filename
from config import Config, COLOR_THEMES, ARTWORK_STYLES, WHISPER_MODELS
from database.db import (
    init_db,
    create_entry,
    get_entry,
    get_all_entries,
    update_entry,
    delete_entry,
    search_entries,
    get_random_prompt,
    get_random_prompts,
    get_entry_count,
    get_setting,
    get_all_settings,
    set_settings_bulk,
    set_setting,
    set_tags,
    set_emotions,
    get_all_frameworks,
    get_framework,
    create_framework,
    get_streak,
    get_top_emotion,
    get_popular_tags,
    get_total_words,
    get_emotion_timeline,
    get_emotion_totals,
    get_streak_calendar,
    get_word_cloud,
    get_framework_usage,
    get_writing_habits,
    get_trends,
    insert_sample_data,
    get_filtered_entries,
    get_filtered_entry_count,
    get_unique_emotions,
    get_unique_entry_types,
    bulk_delete_entries,
    get_entries_for_export,
    get_all_entries_for_export,
    delete_all_entries_data,
    DatabaseError,
    check_database_integrity,
    get_database_stats,
    get_system_prompt,
    update_system_prompt,
    get_all_system_prompts,
    get_daily_question,
    create_daily_question,
    mark_daily_question_answered,
    has_previous_entries,
    replace_daily_question,
    get_dataset_hash,
)
from models.vector_store import (
    add_entry as vector_add,
    search_similar,
    search_semantic,
    find_similar_entries,
    get_all_entry_embeddings,
    get_collection_stats,
    delete_entry as vector_delete,
)
from utils.ai import (
    analyze_entry,
    suggest_title,
    generate_image_prompt,
    generate_deeper_questions,
    generate_summary_and_title,
    detect_emotions,
    identify_patterns,
    generate_artwork_prompt_for_analysis,
    generate_personalized_prompts,
    generate_personalized_prompts_from_embeddings,
    generate_big_five_analysis,
    generate_recurring_topics,
    generate_daily_question,
    suggest_tags,
    generate_baustellen_analysis,
)
from utils.voice import transcribe_audio
from utils.image_gen import (
    generate_image,
    save_image,
    generate_algorithmic_art,
    save_bytes_image,
    build_artwork_prompt,
    generate_svg_placeholder,
)
from utils.services import init_services, refresh_service_status, status, get_detailed_status
from utils.errors import (
    error_response,
    success_response,
    validate_entry_content,
    validate_uuid,
    log_request_error,
    ValidationError,
)
from utils.rate_limit import rate_limit
from utils.i18n import translate as i18n_translate, normalize_language

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# Enable response compression (gzip)
Compress(app)

# Performance logging
perf_log = logging.getLogger('performance')


@app.before_request
def start_timer():
    """Record request start time for performance monitoring."""
    g.start_time = time.time()


@app.after_request
def add_performance_headers(response):
    """Add response timing and cache headers."""
    # Performance timing
    if hasattr(g, 'start_time'):
        elapsed = (time.time() - g.start_time) * 1000
        response.headers['X-Response-Time'] = f"{elapsed:.0f}ms"
        if elapsed > 1000:  # Log slow requests (>1 second)
            perf_log.warning("Slow request: %s took %.0fms", request.path, elapsed)

    # Static file caching headers
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 31536000  # 1 year
        response.cache_control.public = True

    return response


@app.context_processor
def inject_globals():
    """Make theme colors and service status available to every template."""
    settings = _get_settings_with_defaults()
    theme_name = settings.get("color_theme", Config.COLOR_THEME)
    language = normalize_language(settings.get("ui_language") or Config.DEFAULT_LANGUAGE)
    return {
        "theme_colors": COLOR_THEMES.get(theme_name, COLOR_THEMES["ocean"]),
        "theme_name": theme_name,
        "service_status": status,
        "ui_settings": settings,
        "ui_body_classes": _ui_body_classes(settings),
        "ui_language": language,
        "t": lambda key, **kwargs: i18n_translate(key, language, **kwargs),
    }


@app.template_filter('format_date')
def format_date_filter(date_str, lang=None):
    """Format a date string based on language preference.
    
    Args:
        date_str: Date string (ISO format or datetime object)
        lang: Language code ('de' or 'en'). If None, uses current UI language.
    
    Returns:
        Formatted date string:
        - German (de): DD.MM.YYYY (e.g., 30.06.2026)
        - English (en): YYYY-MM-DD (e.g., 2026-06-30)
    """
    if not date_str:
        return ""
    
    # Parse date string
    try:
        if isinstance(date_str, str):
            # Handle both 'YYYY-MM-DD' and full ISO datetime strings
            date_str_clean = date_str[:10] if len(date_str) > 10 else date_str
            date_obj = datetime.fromisoformat(date_str_clean)
        else:
            date_obj = date_str
    except (ValueError, TypeError):
        return date_str
    
    # Get language
    if lang is None:
        lang = _current_language()
    else:
        lang = normalize_language(lang)
    
    # Format based on language
    if lang == 'de':
        # German format: DD.MM.YYYY
        return date_obj.strftime('%d.%m.%Y')
    else:
        # English format: YYYY-MM-DD
        return date_obj.strftime('%Y-%m-%d')


def _current_language():
    return normalize_language(get_setting("ui_language") or Config.DEFAULT_LANGUAGE)


def _t(key, **kwargs):
    return i18n_translate(key, _current_language(), **kwargs)


def _translate_frameworks(frameworks):
    """Translate framework names and descriptions."""
    translated = []
    for fw in frameworks:
        name_key = f"framework.{fw['name'].lower().replace(' ', '_').replace('-', '_')}.name"
        desc_key = f"framework.{fw['name'].lower().replace(' ', '_').replace('-', '_')}.description"
        fw_copy = fw.copy()
        fw_copy['name'] = _t(name_key) or fw['name']
        fw_copy['description'] = _t(desc_key) or fw['description']
        translated.append(fw_copy)
    return translated


def _entry_metadata(entry):
    emotions = [e.get("emotion") for e in entry.get("emotions", []) if e.get("emotion")]
    tags = entry.get("tags") or []
    return {
        "date": entry.get("created_at"),
        "emotions": emotions,
        "word_count": entry.get("word_count"),
        "tags": tags,
    }


def _reindex_entry(entry_id):
    entry = get_entry(entry_id)
    if not entry:
        return
    vector_add(entry_id, entry.get("content", ""), metadata=_entry_metadata(entry))


def _recency_score(date_str):
    if not date_str:
        return 0.0
    try:
        entry_date = datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return 0.0
    days_ago = max(0, (datetime.now() - entry_date).days)
    return 1 / (1 + (days_ago / 30))


def _infer_sentiment(emotions):
    if not emotions:
        return "neutral"
    positive = {"joy", "trust", "anticipation"}
    negative = {"fear", "sadness", "anger", "disgust"}
    seen = {e.get("emotion") for e in emotions if isinstance(e, dict)}
    has_pos = any(e in positive for e in seen)
    has_neg = any(e in negative for e in seen)
    if has_pos and has_neg:
        return "mixed"
    if has_pos:
        return "positive"
    if has_neg:
        return "negative"
    return "neutral"


def _normalize_style(style):
    if not style:
        return ""
    cleaned = str(style).strip().lower().replace("_", " ").replace("-", " ")
    return cleaned


def _settings_defaults():
    return {
        "username": "",
        "default_entry_type": "blank",
        "auto_save_interval": "30",
        "ollama_model": Config.OLLAMA_MODEL,
        "emotion_analysis_enabled": "true",
        "go_deeper_enabled": "true",
        "past_memories_enabled": "true",
        "artwork_enabled": "true",
        "sd_default_style": Config.SD_DEFAULT_STYLE,
        "whisper_model": Config.WHISPER_MODEL,
        "voice_auto_edit": "true",
        "voice_language": "auto",
        "ui_language": normalize_language(Config.DEFAULT_LANGUAGE),
        "theme_mode": "auto",
        "color_theme": Config.COLOR_THEME,
        "font_size": "medium",
        "spacing_density": "comfortable",
        "journal_view": "list",
        "local_only_mode": "false",
        "backup_location": "",
        "retention_period": "all",
        "db_path": Config.DATABASE_PATH,
        "chroma_path": Config.CHROMA_PATH,
        "model_cache_location": Config.MODEL_PATH,
        "debug_mode": str(Config.DEBUG).lower(),
        "llm_provider": Config.LLM_PROVIDER,
        "ollama_base_url": Config.OLLAMA_BASE_URL,
        "lmstudio_base_url": Config.LMSTUDIO_BASE_URL,
        "lmstudio_model": Config.LMSTUDIO_MODEL,
        "sd_endpoint": Config.SD_API_URL,
    }


def _get_settings_with_defaults():
    defaults = _settings_defaults()
    stored = get_all_settings()
    merged = {**defaults, **stored}
    return merged


def _ui_body_classes(settings):
    classes = []
    font_size = settings.get("font_size", "medium")
    spacing = settings.get("spacing_density", "comfortable")
    if font_size == "small":
        classes.append("ui-font-small")
    elif font_size == "large":
        classes.append("ui-font-large")
    else:
        classes.append("ui-font-medium")
    if spacing == "compact":
        classes.append("ui-compact")
    else:
        classes.append("ui-comfortable")
    return " ".join(classes)


def _coerce_bool(value, default=False):
    if value is None:
        return default
    cleaned = str(value).strip().lower()
    if cleaned in {"true", "1", "yes", "on"}:
        return True
    if cleaned in {"false", "0", "no", "off"}:
        return False
    return default


def _is_local_url(url):
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def _local_only_block(url):
    return get_setting("local_only_mode", "false") == "true" and not _is_local_url(url)


def _validate_settings(values):
    errors = []
    cleaned = {}
    defaults = _settings_defaults()

    def expect_enum(key, allowed):
        value = values.get(key, defaults.get(key))
        if value not in allowed:
            errors.append(f"{key} must be one of: {', '.join(allowed)}")
            value = defaults.get(key)
        cleaned[key] = value

    cleaned["username"] = values.get("username", "").strip()

    expect_enum("default_entry_type", ["blank", "framework", "prompt"])
    expect_enum("auto_save_interval", ["disabled", "15", "30", "60"])
    expect_enum("theme_mode", ["light", "dark", "auto"])
    expect_enum("color_theme", list(COLOR_THEMES.keys()))
    expect_enum("font_size", ["small", "medium", "large"])
    expect_enum("spacing_density", ["compact", "comfortable"])
    expect_enum("journal_view", ["grid", "list"])
    expect_enum("ui_language", ["de", "en"])
    expect_enum("retention_period", ["all", "1_year", "2_years"])
    expect_enum("sd_default_style", ARTWORK_STYLES)
    expect_enum("whisper_model", ["tiny", "base", "small", "medium"])

    cleaned["ollama_model"] = values.get("ollama_model", defaults["ollama_model"]).strip() or defaults["ollama_model"]
    cleaned["ollama_base_url"] = values.get("ollama_base_url", defaults["ollama_base_url"]).strip() or defaults["ollama_base_url"]
    cleaned["sd_endpoint"] = values.get("sd_endpoint", defaults["sd_endpoint"]).strip() or defaults["sd_endpoint"]

    cleaned["emotion_analysis_enabled"] = str(_coerce_bool(values.get("emotion_analysis_enabled"), True)).lower()
    cleaned["go_deeper_enabled"] = str(_coerce_bool(values.get("go_deeper_enabled"), True)).lower()
    cleaned["past_memories_enabled"] = str(_coerce_bool(values.get("past_memories_enabled"), True)).lower()
    cleaned["artwork_enabled"] = str(_coerce_bool(values.get("artwork_enabled"), True)).lower()
    cleaned["voice_auto_edit"] = str(_coerce_bool(values.get("voice_auto_edit"), True)).lower()
    cleaned["local_only_mode"] = str(_coerce_bool(values.get("local_only_mode"), False)).lower()
    cleaned["debug_mode"] = str(_coerce_bool(values.get("debug_mode"), Config.DEBUG)).lower()

    cleaned["voice_language"] = values.get("voice_language", defaults["voice_language"]).strip() or defaults["voice_language"]
    cleaned["backup_location"] = values.get("backup_location", "").strip()
    cleaned["db_path"] = values.get("db_path", defaults["db_path"]).strip() or defaults["db_path"]
    cleaned["chroma_path"] = values.get("chroma_path", defaults["chroma_path"]).strip() or defaults["chroma_path"]
    cleaned["model_cache_location"] = values.get("model_cache_location", defaults["model_cache_location"]).strip() or defaults["model_cache_location"]

    if not cleaned["ollama_model"]:
        errors.append("ollama_model cannot be empty")
    if not cleaned["db_path"]:
        errors.append("db_path cannot be empty")
    if not cleaned["chroma_path"]:
        errors.append("chroma_path cannot be empty")

    return cleaned, errors


def _restart_warning_keys():
    return {
        "db_path": "Database path change requires restart.",
        "chroma_path": "ChromaDB path change requires restart.",
        "model_cache_location": "Model cache change requires restart.",
        "debug_mode": "Debug mode change requires restart.",
        "ollama_base_url": "Ollama endpoint change requires restart.",
        "sd_endpoint": "Stable Diffusion endpoint change requires restart.",
        "whisper_model": "Whisper model change requires restart.",
    }


def _get_ollama_models():
    url = f"{Config.OLLAMA_BASE_URL}/api/tags"
    try:
        resp = requests.get(url, timeout=4)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return [m.get("name") for m in models if m.get("name")]
    except Exception:
        return []


def _entries_to_markdown(entries):
    lines = ["# Journal Export", ""]
    for entry in entries:
        created_at = entry.get("created_at", "")
        summary = entry.get("summary") or ""
        content = entry.get("content") or ""
        tags = ", ".join(entry.get("tags", []))
        emotions = ", ".join([e.get("emotion") for e in entry.get("emotions", []) if e.get("emotion")])
        lines.append(f"## {summary or created_at or 'Entry'}")
        if created_at:
            lines.append(f"- Date: {created_at}")
        if entry.get("entry_type"):
            lines.append(f"- Type: {entry.get('entry_type')}")
        if tags:
            lines.append(f"- Tags: {tags}")
        if emotions:
            lines.append(f"- Emotions: {emotions}")
        lines.append("")
        lines.append(content)
        lines.append("\n---\n")
    return "\n".join(lines)


def _entry_summary_snippet(entry, max_len=240):
    summary = entry.get("summary") or ""
    if summary:
        return summary.strip()
    content = entry.get("content", "")
    snippet = content.strip().replace("\n", " ")
    if len(snippet) > max_len:
        snippet = snippet[:max_len].rstrip() + "..."
    return snippet


def _settings_export_payload():
    settings = get_all_settings()
    return {
        "settings": settings,
        "exported_at": datetime.now().isoformat(),
        "version": 1,
    }


def _parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _parse_range_days(value, default=30, allowed=(7, 30, 60, 90, 180, 365)):
    if not value:
        return default
    cleaned = str(value).strip().lower()
    if cleaned.endswith("d"):
        cleaned = cleaned[:-1]
    try:
        days = int(cleaned)
    except (TypeError, ValueError):
        return default
    if days in allowed:
        return days
    return default


def _range_to_dates(range_value):
    if not range_value or str(range_value).lower() == "all":
        return None, None
    days = _parse_range_days(range_value, default=30)
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.date().isoformat(), end.date().isoformat()


def _cosine_similarity(vec_a, vec_b):
    if not vec_a or not vec_b:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def _cluster_embeddings(records, similarity_threshold=0.78, max_records=200):
    filtered = [r for r in records if r.get("embedding") is not None]
    filtered.sort(key=lambda r: r.get("metadata", {}).get("date", ""), reverse=True)
    filtered = filtered[:max_records]

    clusters = []

    def centroid(cluster):
        return [v / cluster["count"] for v in cluster["sum_vector"]]

    for rec in filtered:
        emb = rec.get("embedding")
        if emb is None:
            continue
        assigned = False
        for cluster in clusters:
            sim = _cosine_similarity(emb, centroid(cluster))
            if sim >= similarity_threshold:
                for i, val in enumerate(emb):
                    cluster["sum_vector"][i] += val
                cluster["count"] += 1
                cluster["entries"].append(rec)
                assigned = True
                break
        if not assigned:
            clusters.append({
                "sum_vector": list(emb),
                "count": 1,
                "entries": [rec],
            })

    return clusters


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Setup Wizard (First-Run)
# ---------------------------------------------------------------------------


@app.route("/setup")
def setup_wizard():
    """Show the first-run setup wizard."""
    return render_template("setup_wizard.html", themes=COLOR_THEMES)


@app.route("/setup/complete", methods=["POST"])
def setup_complete():
    """Save initial settings from setup wizard."""
    settings_to_save = {}

    color_theme = request.form.get("color_theme")
    if color_theme and color_theme in COLOR_THEMES:
        settings_to_save["color_theme"] = color_theme

    theme_mode = request.form.get("theme_mode")
    if theme_mode in ("light", "dark", "system"):
        settings_to_save["theme_mode"] = theme_mode

    entry_type = request.form.get("default_entry_type")
    if entry_type in ("blank", "prompt", "framework"):
        settings_to_save["default_entry_type"] = entry_type

    # Mark setup as complete
    settings_to_save["setup_complete"] = "true"

    if settings_to_save:
        set_settings_bulk(settings_to_save)

    return jsonify({"success": True})


@app.route("/")
def dashboard():
    """Main dashboard showing overview stats and recent entries."""
    # Check if first run (setup not complete)
    setup_complete = get_setting("setup_complete", "false")
    if setup_complete != "true":
        return redirect(url_for("setup_wizard"))

    recent = get_all_entries(limit=3)
    count = get_entry_count()
    # Only show the "Last week" suggestions label when there is enough recent data.
    last_week_start = (datetime.now() - timedelta(days=7)).date().isoformat()
    today = datetime.now().date().isoformat()
    last_week_count = get_filtered_entry_count(date_from=last_week_start, date_to=today)
    has_last_week_suggestions = last_week_count >= 3
    prompts = get_random_prompts(3)
    streak = get_streak()
    top_emotion = get_top_emotion()
    popular_tags = get_popular_tags(8)
    total_words = get_total_words()
    frameworks = _translate_frameworks(get_all_frameworks())
    return render_template(
        "dashboard.html",
        entries=recent,
        entry_count=count,
        has_last_week_suggestions=has_last_week_suggestions,
        prompts=prompts,
        streak=streak,
        top_emotion=top_emotion,
        popular_tags=popular_tags,
        total_words=total_words,
        frameworks=frameworks,
    )


@app.route("/entry/new", methods=["GET", "POST"])
def new_entry():
    """Create a new journal entry."""
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        entry_type = request.form.get("entry_type", "text")
        framework_id = request.form.get("framework_id") or None
        tags_raw = request.form.get("tags", "").strip()

        if not content:
            return render_template(
                "entry_form.html",
                error="Content is required.",
                prompt=get_random_prompt(),
                frameworks=_translate_frameworks(get_all_frameworks()),
            )

        if len(content) > Config.MAX_ENTRY_LENGTH:
            return render_template(
                "entry_form.html",
                error=f"Entry exceeds maximum length of {Config.MAX_ENTRY_LENGTH:,} characters.",
                prompt=get_random_prompt(),
                frameworks=_translate_frameworks(get_all_frameworks()),
            )

        if framework_id:
            framework_id = int(framework_id)

        # Generate title using AI if Ollama is available
        entry_title = None
        if status.ollama:
            try:
                entry_title = suggest_title(content)
            except Exception as e:
                log.warning("Failed to generate title: %s", e)

        entry_id = create_entry(
            content,
            entry_type=entry_type,
            framework_id=framework_id,
            title=entry_title,
        )

        # Save tags
        if tags_raw:
            set_tags(entry_id, tags_raw.split(","))

        # Index in vector store (with metadata)
        _reindex_entry(entry_id)

        return redirect(url_for("view_entry", entry_id=entry_id))

    category = request.args.get("category")
    daily_question = request.args.get("daily_question")
    default_pref = get_setting("default_entry_type", "blank")
    if request.args.get("framework"):
        default_pref = "framework"

    # If daily_question is provided, use it as the prompt
    if daily_question:
        prompt = {"category": "Daily Reflection", "text": daily_question}
    else:
        prompt = get_random_prompt(category) if (category or default_pref == "prompt") else None

    return render_template(
        "entry_form.html",
        prompt=prompt,
        frameworks=_translate_frameworks(get_all_frameworks()),
        default_entry_type=default_pref,
    )


@app.route("/entry/<entry_id>")
def view_entry(entry_id):
    """View a single journal entry."""
    entry = get_entry(entry_id)
    if not entry:
        return render_template("404.html"), 404
    similar = search_similar(entry["content"], n_results=3)
    # Resolve similar entry records
    similar_entries = []
    for s in similar:
        if s["entry_id"] != entry_id:
            e = get_entry(s["entry_id"])
            if e:
                similar_entries.append(e)
    default_style = get_setting("sd_default_style", Config.SD_DEFAULT_STYLE)
    return render_template(
        "entry_view.html",
        entry=entry,
        similar=similar_entries,
        style_options=ARTWORK_STYLES,
        default_style=default_style,
    )


@app.route("/entry/<entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id):
    """Edit an existing journal entry."""
    entry = get_entry(entry_id)
    if not entry:
        return render_template("404.html"), 404

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        entry_type = request.form.get("entry_type", "text")
        framework_id = request.form.get("framework_id") or None
        tags_raw = request.form.get("tags", "").strip()

        if len(content) > Config.MAX_ENTRY_LENGTH:
            return render_template(
                "entry_form.html",
                entry=entry,
                editing=True,
                error=f"Entry exceeds maximum length of {Config.MAX_ENTRY_LENGTH:,} characters.",
                frameworks=_translate_frameworks(get_all_frameworks()),
            )

        if framework_id:
            framework_id = int(framework_id)

        update_entry(
            entry_id,
            content=content,
            entry_type=entry_type,
            framework_id=framework_id,
        )

        # Update tags
        set_tags(entry_id, tags_raw.split(",") if tags_raw else [])

        # Re-index in vector store (with metadata)
        _reindex_entry(entry_id)

        return redirect(url_for("view_entry", entry_id=entry_id))

    return render_template(
        "entry_form.html",
        entry=entry,
        editing=True,
        frameworks=_translate_frameworks(get_all_frameworks()),
    )


@app.route("/entry/<entry_id>/delete", methods=["POST"])
def remove_entry(entry_id):
    """Delete a journal entry."""
    delete_entry(entry_id)
    vector_delete(entry_id)
    return redirect(url_for("journal"))


@app.route("/journal")
def journal():
    """Show all journal entries with filtering, sorting, and pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    sort_by = request.args.get("sort", "created_at")
    sort_dir = request.args.get("dir", "DESC")
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    filter_emotions = request.args.getlist("emotions")
    filter_tags = request.args.getlist("tags")
    filter_entry_types = request.args.getlist("entry_types")
    filter_framework_ids = [
        int(fid) for fid in request.args.getlist("framework_ids") if fid.isdigit()
    ]

    entries = get_filtered_entries(
        limit=per_page,
        offset=(page - 1) * per_page,
        sort_by=sort_by,
        sort_dir=sort_dir,
        date_from=date_from,
        date_to=date_to,
        emotions=filter_emotions or None,
        tags=filter_tags or None,
        entry_types=filter_entry_types or None,
        framework_ids=filter_framework_ids or None,
    )
    count = get_filtered_entry_count(
        date_from=date_from,
        date_to=date_to,
        emotions=filter_emotions or None,
        tags=filter_tags or None,
        entry_types=filter_entry_types or None,
        framework_ids=filter_framework_ids or None,
    )
    total_pages = max(1, (count + per_page - 1) // per_page)

    filters = {
        "sort": sort_by,
        "dir": sort_dir,
        "date_from": date_from or "",
        "date_to": date_to or "",
        "emotions": filter_emotions,
        "tags": filter_tags,
        "entry_types": filter_entry_types,
        "framework_ids": filter_framework_ids,
    }
    has_active_filters = any([
        date_from, date_to, filter_emotions, filter_tags,
        filter_entry_types, filter_framework_ids,
    ])

    all_emotions = get_unique_emotions()
    all_tags = get_popular_tags(30)
    all_entry_types = get_unique_entry_types()
    frameworks = _translate_frameworks(get_all_frameworks())

    return render_template(
        "journal.html",
        entries=entries,
        page=page,
        total_pages=total_pages,
        entry_count=count,
        filters=filters,
        has_active_filters=has_active_filters,
        all_emotions=all_emotions,
        all_tags=all_tags,
        all_entry_types=all_entry_types,
        frameworks=frameworks,
    )


@app.route("/ask")
def ask():
    """Ask questions across journal entries or a specific entry."""
    entry_id = request.args.get("entry_id")
    entry = None
    if entry_id:
        entry = get_entry(entry_id)
        if not entry:
            return render_template("404.html"), 404
    return render_template("ask.html", entry=entry)


@app.route("/search")
def search():
    """Search entries by keyword or semantic similarity."""
    query = request.args.get("q", "").strip()
    mode = request.args.get("mode", "keyword")
    results = []
    if query:
        if mode == "semantic":
            semantic_hits = search_semantic(query, n_results=30)
            scored = []
            for hit in semantic_hits:
                entry = get_entry(hit["entry_id"])
                if not entry:
                    continue
                similarity = hit.get("similarity_score", 0)
                recency = _recency_score(entry.get("created_at"))
                score = (similarity * 0.7) + (recency * 0.3)
                scored.append((score, entry))
            scored.sort(key=lambda item: item[0], reverse=True)
            results = [entry for _, entry in scored[:10]]
        else:
            results = search_entries(query)
    return render_template("search.html", query=query, mode=mode, results=results)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Application settings page."""
    framework_message = None
    framework_error = None
    settings_message = None
    settings_errors = []
    restart_warnings = []
    settings_data = _get_settings_with_defaults()
    if request.method == "POST":
        action = request.form.get("action", "settings")
        if action == "add_framework":
            name = request.form.get("framework_name", "").strip()
            description = request.form.get("framework_description", "").strip()
            category = request.form.get("framework_category", "").strip()
            questions_raw = request.form.get("framework_questions", "")

            question_lines = [line.strip() for line in questions_raw.splitlines() if line.strip()]

            if not name:
                framework_error = "Framework name is required."
            elif not question_lines:
                framework_error = "Add at least one question."
            else:
                questions = [
                    {
                        "id": f"q{idx}",
                        "question": line,
                        "placeholder": "Your response...",
                        "type": "textarea",
                        "required": False,
                    }
                    for idx, line in enumerate(question_lines, start=1)
                ]
                create_framework(name, description, questions, category)
                return redirect(url_for("settings", fw="added"))
        else:
            form_values = request.form.to_dict(flat=True)
            boolean_keys = {
                "emotion_analysis_enabled",
                "go_deeper_enabled",
                "past_memories_enabled",
                "artwork_enabled",
                "voice_auto_edit",
                "local_only_mode",
                "debug_mode",
            }
            for key in boolean_keys:
                form_values[key] = "true" if request.form.get(key) else "false"

            cleaned, errors = _validate_settings(form_values)
            if errors:
                settings_errors = errors
                settings_data = {**_settings_defaults(), **form_values}
            else:
                previous = _get_settings_with_defaults()
                set_settings_bulk(cleaned)
                settings_message = "Settings saved."
                settings_data = {**_settings_defaults(), **cleaned}
                for key, message in _restart_warning_keys().items():
                    if previous.get(key) != cleaned.get(key):
                        restart_warnings.append(message)

    if request.args.get("fw") == "added":
        framework_message = "Framework saved."
    if request.method == "GET":
        settings_data = _get_settings_with_defaults()
    services = status.summary(_current_language())
    ollama_models = _get_ollama_models() if status.ollama else []
    frameworks = _translate_frameworks(get_all_frameworks())

    # System prompts for the prompt editor section
    system_prompts = get_all_system_prompts()

    # Extract {placeholder} variables from each prompt for display
    prompt_placeholders = {}
    for sp in system_prompts:
        matches = re.findall(r'\{(\w+)\}', sp.get("prompt_text", ""))
        prompt_placeholders[sp["key"]] = list(dict.fromkeys(matches))  # unique, order-preserved

    # Get current language for i18n
    lang = _current_language()
    
    # Group prompts by WHERE they are processed in the application
    # This helps users understand which prompts affect which features
    # Keys map to i18n keys
    prompt_categories_keys = {
        "entry": [
            "analyze_entry",
            "generate_summary_and_title",
            "detect_emotions",
            "identify_patterns",
            "generate_artwork_prompt",
            "generate_deeper_questions",
            "generate_deeper_questions_followup",
            "tag_extraction",
            "suggest_title",
        ],
        "dashboard": [
            "daily_reflection_question",
            "generate_personalized_prompts",
            "generate_personalized_prompts_embeddings",
        ],
        "insights": [
            "generate_big_five_analysis",
            "generate_recurring_topics",
            "identify_baustellen",
        ],
        "chat": [
            "chat_persona_entry",
            "chat_persona_global",
        ],
        "image": [
            "generate_image_prompt",
        ],
        "legacy": [
            "emotion_summary",
            "image_generation",
        ],
    }
    
    # Build translated category names and descriptions
    prompt_categories = {}
    prompt_category_descriptions = {}
    for key, prompt_list in prompt_categories_keys.items():
        cat_name = i18n_translate(f"ui.settings.category.{key}", lang)
        cat_desc = i18n_translate(f"ui.settings.category_desc.{key}", lang)
        prompt_categories[cat_name] = prompt_list
        prompt_category_descriptions[cat_name] = cat_desc

    return render_template(
        "settings.html",
        settings=settings_data,
        services=services,
        ollama_models=ollama_models,
        theme_options=list(COLOR_THEMES.keys()),
        style_options=ARTWORK_STYLES,
        whisper_options=["tiny", "base", "small", "medium"],
        frameworks=frameworks,
        framework_message=framework_message,
        framework_error=framework_error,
        settings_message=settings_message,
        settings_errors=settings_errors,
        restart_warnings=restart_warnings,
        system_prompts=system_prompts,
        prompt_categories=prompt_categories,
        prompt_placeholders=prompt_placeholders,
        prompt_category_descriptions=prompt_category_descriptions,
    )


# ---------------------------------------------------------------------------
# API endpoints (used by frontend JS)
# ---------------------------------------------------------------------------


@app.route("/api/analyze", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60)
def api_analyze():
    """AI-analyze a journal entry and store as summary."""
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    content = data.get("content", "")
    is_valid, error_msg = validate_entry_content(content)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Check if Ollama is available
    if not status.ollama:
        return jsonify({
            "error": "AI analysis is currently unavailable.",
            "details": status.ollama_message,
            "recoverable": True,
        }), 503

    analysis = analyze_entry(content)
    if not isinstance(analysis, str):
        analysis = str(analysis or "")

    # Check for AI error in response
    if analysis.startswith("[Error"):
        return jsonify({"error": analysis.strip("[]"), "recoverable": True}), 503

    entry_id = data.get("entry_id")
    if entry_id:
        is_valid_id, id_error = validate_uuid(entry_id, "entry_id")
        if is_valid_id:
            update_entry(entry_id, summary=analysis)

    return jsonify({"analysis": analysis})


@app.route("/api/suggest-title", methods=["POST"])
def api_suggest_title():
    """Suggest a summary title for journal content."""
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403
    data = request.get_json()
    content = data.get("content", "")
    if not content:
        return jsonify({"error": "No content provided"}), 400
    title = suggest_title(content)
    return jsonify({"title": title})


@app.route("/api/transcribe", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60)
def api_transcribe():
    """Transcribe uploaded audio to text."""
    if "audio" not in request.files:
        return jsonify({
            "error": "No audio file provided",
            "error_type": "validation",
            "guidance": "Please record or upload an audio file.",
        }), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({
            "error": "Invalid audio file",
            "error_type": "validation",
        }), 400

    # Read the audio bytes
    audio_bytes = audio_file.read()

    # Check if Whisper is available
    if not status.whisper:
        return jsonify({
            "error": "Voice transcription is not available.",
            "error_type": "service",
            "guidance": status.whisper_message,
            "recoverable": False,
        }), 503

    # Get optional language preference
    language = request.form.get("language", None)

    result = transcribe_audio(audio_bytes, filename=audio_file.filename, language=language)

    if "error" in result:
        status_code = 503 if result.get("error_type") == "service" else 400
        return jsonify(result), status_code

    return jsonify(result)


@app.route("/api/generate-image", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=60)
def api_generate_image():
    """Generate an image for a journal entry using Stable Diffusion."""
    if get_setting("artwork_enabled", "true") != "true":
        return jsonify({"error": "Artwork generation is disabled in settings."}), 403
    data = request.get_json()
    content = data.get("content", "")
    entry_id = data.get("entry_id")
    if not content:
        return jsonify({"error": "No content provided"}), 400

    filename = f"entry_{entry_id or 'temp'}.png"
    url = None
    prompt_used = None
    model_used = "sd"

    # Use Stable Diffusion for image generation
    if not _local_only_block(Config.SD_API_URL) and status.stable_diffusion:
        sd_prompt = generate_image_prompt(content)
        prompt_used = sd_prompt
        image_b64 = generate_image(sd_prompt)
        if image_b64:
            url = save_image(image_b64, filename)

    if not url:
        return jsonify({
            "error": "Image generation failed. Stable Diffusion is unavailable."
        }), 503

    if entry_id:
        update_entry(entry_id, artwork_path=url)

    return jsonify({
        "image_url": url,
        "prompt_used": prompt_used,
        "model_used": model_used,
    })


@app.route("/api/generate/artwork", methods=["POST"])
def api_generate_artwork():
    """Generate privacy-preserving artwork for an entry using Stable Diffusion."""
    if get_setting("artwork_enabled", "true") != "true":
        return jsonify({"error": "Artwork generation is disabled in settings."}), 403
    data = request.get_json() or {}
    entry_id = data.get("entry_id")
    style_raw = data.get("style")
    regenerate = bool(data.get("regenerate", False))

    if not entry_id:
        return jsonify({"error": "entry_id is required"}), 400

    entry = get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404

    style = _normalize_style(style_raw) or get_setting("sd_default_style", Config.SD_DEFAULT_STYLE)
    style = _normalize_style(style)
    if style not in ARTWORK_STYLES:
        style = Config.SD_DEFAULT_STYLE

    if not regenerate and entry.get("artwork_path") and entry.get("artwork_style") == style:
        return jsonify({
            "image_url": entry.get("artwork_path"),
            "generation_time": 0,
        })

    emotions = entry.get("emotions", [])
    themes = entry.get("tags") or []
    if not themes:
        themes = ["reflection"]
    sentiment = _infer_sentiment(emotions)

    start_time = time.time()
    filename_base = f"artwork_{entry_id}_{int(time.time())}"
    url = None
    used_model = "sd"

    # Priority 1: Try Stable Diffusion
    if status.stable_diffusion:
        prompt = build_artwork_prompt(style, themes=themes, emotions=emotions, sentiment=sentiment)
        log.info("Generating SD artwork for entry %s", entry_id)
        image_b64 = generate_image(prompt, style=style)
        if image_b64:
            url = save_image(image_b64, f"{filename_base}.png")

    # Priority 2: Algorithmic art (local, privacy-preserving)
    if not url:
        used_model = "algorithmic"
        seed = f"{entry_id}:{style}:{int(time.time()) if regenerate else 0}"
        art_bytes = generate_algorithmic_art(style, emotions=emotions, themes=themes, seed=seed)
        if art_bytes:
            url = save_bytes_image(art_bytes, f"{filename_base}.png")

    # Priority 4: SVG placeholder (last resort)
    if not url:
        used_model = "svg"
        seed = f"{entry_id}:{style}:{int(time.time()) if regenerate else 0}"
        svg_bytes = generate_svg_placeholder(style, emotions=emotions, themes=themes, seed=seed)
        url = save_bytes_image(svg_bytes, f"{filename_base}.svg")

    generation_time = round(time.time() - start_time, 2)
    update_entry(entry_id, artwork_path=url, artwork_style=style)

    return jsonify({
        "image_url": url,
        "generation_time": generation_time,
        "model_used": used_model,
    })


@app.route("/api/upload/artwork", methods=["POST"])
def api_upload_artwork():
    """Upload a custom artwork image for an entry."""
    entry_id = request.form.get("entry_id")
    if not entry_id:
        return jsonify({"error": "entry_id is required"}), 400
    entry = get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404

    if "image" not in request.files:
        return jsonify({"error": "No image file"}), 400

    image = request.files["image"]
    if not image.filename:
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(image.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return jsonify({"error": "Unsupported file type"}), 400

    safe_name = f"artwork_{entry_id}_{int(time.time())}{ext}"
    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, safe_name)
    image.save(filepath)

    url = f"/static/uploads/{safe_name}"
    update_entry(entry_id, artwork_path=url, artwork_style="uploaded")
    return jsonify({"image_url": url})


@app.route("/api/delete/artwork", methods=["POST"])
def api_delete_artwork():
    """Delete/reset the artwork for an entry."""
    data = request.get_json()
    entry_id = data.get("entry_id")
    if not entry_id:
        return jsonify({"error": "entry_id is required"}), 400
    
    entry = get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404
    
    # Clear the artwork_path and artwork_style
    update_entry(entry_id, artwork_path=None, artwork_style=None)
    return jsonify({"success": True})


@app.route("/api/prompt")
def api_prompt():
    """Get a random journal prompt."""
    category = request.args.get("category")
    prompt = get_random_prompt(category)
    if prompt:
        return jsonify({"category": prompt["category"], "text": prompt["text"]})
    return jsonify({"error": "No prompts found"}), 404


@app.route("/api/insights/emotions")
def api_insights_emotions():
    """Return emotion timelines and wheel totals."""
    range_days = _parse_range_days(request.args.get("range"), default=90)
    timeline = get_emotion_timeline(range_days=range_days)
    totals = get_emotion_totals()
    return jsonify({
        "range_days": range_days,
        "timeline": timeline,
        "wheel": totals,
    })


@app.route("/api/insights/big-five")
def api_insights_big_five():
    """Return Big Five personality analysis for a timeframe."""
    range_value = request.args.get("range", "30")
    date_from, date_to = _range_to_dates(range_value)

    # Check cache based on dataset hash (count + last modified)
    current_hash = get_dataset_hash(date_from, date_to)
    cache_key = f"big_five_cache_{range_value}"

    cached_raw = get_setting(cache_key)
    if cached_raw:
        try:
            cached_obj = json.loads(cached_raw)
            if cached_obj.get("hash") == current_hash:
                return jsonify(cached_obj.get("data"))
        except (ValueError, TypeError):
            pass

    entries = get_filtered_entries(
        limit=80,
        offset=0,
        sort_by="created_at",
        sort_dir="DESC",
        date_from=date_from,
        date_to=date_to,
    )
    summaries = [_entry_summary_snippet(e) for e in entries if e.get("content")]
    
    # Only analyze if there are sufficient entries
    if len(summaries) < 3:
        return jsonify({
            "error": _t("insights.big_five.not_enough_entries"),
            "message": _t("insights.big_five.min_entries")
        }), 200
    
    label = "Overall" if not date_from else f"Last {range_value} days"
    result = generate_big_five_analysis(summaries, label)

    if "error" in result:
        status_code = 503 if "not available" in result["error"].lower() else 400
        return jsonify(result), status_code

    # Cache the successful result
    try:
        cache_payload = json.dumps({"hash": current_hash, "data": result})
        set_setting(cache_key, cache_payload)
    except Exception as e:
        log.warning("Failed to cache Big Five results: %s", e)

    return jsonify(result)


@app.route("/api/insights/baustellen")
def api_insights_baustellen():
    """Return active Baustellen (ongoing concerns) with smart caching."""
    range_value = request.args.get("range", "60")  # Default 60 days
    date_from, date_to = _range_to_dates(range_value)
    
    # Smart caching: check if data changed
    current_hash = get_dataset_hash(date_from, date_to)
    cache_key = f"baustellen_cache_{range_value}"
    
    cached_raw = get_setting(cache_key)
    if cached_raw:
        try:
            cached_obj = json.loads(cached_raw)
            if cached_obj.get("hash") == current_hash:
                return jsonify(cached_obj.get("data"))
        except (ValueError, TypeError):
            pass
    
    # Fetch entries for analysis
    entries = get_filtered_entries(
        limit=100,  # More entries for better pattern detection
        offset=0,
        sort_by="created_at",
        sort_dir="DESC",
        date_from=date_from,
        date_to=date_to,
    )
    
    # Prepare content snippets with metadata
    entry_data = []
    for e in entries:
        if e.get("content"):
            entry_data.append({
                "id": e.get("id"),
                "date": e.get("created_at"),
                "content": _entry_summary_snippet(e, max_len=200),
                "tags": e.get("tags", []),
                "emotions": [em.get("emotion") for em in e.get("emotions", [])]
            })
    
    # Only analyze if there are sufficient entries
    if len(entry_data) < 5:
        return jsonify({
            "baustellen": [],
            "message": _t("insights.issues.min_entries")
        })
    
    # Generate Baustellen analysis
    result = generate_baustellen_analysis(entry_data)
    
    if "error" in result:
        error_text = str(result.get("error", ""))
        status_code = 503 if "not available" in error_text.lower() else 400
        return jsonify(result), status_code
    
    # Cache successful result
    try:
        cache_payload = json.dumps({"hash": current_hash, "data": result})
        set_setting(cache_key, cache_payload)
    except Exception as e:
        log.warning("Failed to cache Baustellen results: %s", e)
    
    return jsonify(result)


@app.route("/api/insights/recurring-topics")
def api_recurring_topics():
    """Return recurring topics with insights."""
    records = get_all_entry_embeddings()
    if not records:
        return jsonify({"topics": []})
    clusters = _cluster_embeddings(records)
    topic_inputs = []
    for cluster in clusters[:6]:
        entries = cluster.get("entries", [])
        if not entries:
            continue
        entry_id = entries[0].get("entry_id")
        entry = get_entry(entry_id) if entry_id else None
        label = None
        if entry:
            label = (entry.get("tags") or [None])[0] or entry.get("summary") or "Recurring theme"
        examples = []
        for item in entries[:3]:
            entry_match = get_entry(item.get("entry_id"))
            if entry_match:
                examples.append(_entry_summary_snippet(entry_match, max_len=140))
        topic_inputs.append({
            "topic": label or "Recurring theme",
            "examples": examples,
        })

    # Only analyze if there are topics to process
    if not topic_inputs:
        return jsonify({"topics": []})

    result = generate_recurring_topics(topic_inputs)
    if "error" in result:
        error_text = str(result.get("error", ""))
        status_code = 503 if "not available" in error_text.lower() else 400
        return jsonify(result), status_code
    return jsonify(result)


@app.route("/api/insights/writing-patterns")
def api_insights_writing_patterns():
    """Return streak calendar, word cloud, and writing habits."""
    range_days = _parse_range_days(request.args.get("range"), default=180)
    streak_calendar = get_streak_calendar(range_days=range_days)
    word_cloud = get_word_cloud(range_days=max(range_days, 90))
    habits = get_writing_habits(range_days=range_days)
    return jsonify({
        "range_days": range_days,
        "streak_calendar": streak_calendar,
        "word_cloud": word_cloud,
        "habits": habits,
    })


@app.route("/api/insights/frameworks")
def api_insights_frameworks():
    """Return framework usage stats."""
    data = get_framework_usage()
    return jsonify(data)


@app.route("/api/insights/trends")
def api_insights_trends():
    """Return personal growth trend signals."""
    range_days = _parse_range_days(request.args.get("range"), default=180)
    data = get_trends(range_days=range_days)
    data["range_days"] = range_days
    return jsonify(data)


@app.route("/api/search/semantic", methods=["POST"])
def api_search_semantic():
    """Semantic search across all entries with recency-aware reranking."""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    limit = min(int(data.get("limit", 10)), 20)
    if not query:
        return jsonify({"error": "query is required"}), 400

    raw_results = search_semantic(query, n_results=min(limit * 3, 60))
    scored = []
    for hit in raw_results:
        entry = get_entry(hit.get("entry_id"))
        if not entry:
            continue
        similarity = hit.get("similarity_score", 0)
        recency = _recency_score(entry.get("created_at"))
        score = (similarity * 0.7) + (recency * 0.3)
        title = entry.get("summary") or entry.get("content", "")[:60].strip()
        excerpt_source = entry.get("content", "")
        excerpt = excerpt_source[:200] + ("..." if len(excerpt_source) > 200 else "")
        scored.append({
            "entry_id": entry.get("id"),
            "title": title or "Untitled",
            "date": entry.get("created_at"),
            "excerpt": excerpt,
            "similarity_score": similarity,
            "_score": score,
        })

    scored.sort(key=lambda item: item["_score"], reverse=True)
    results = [
        {
            "entry_id": item["entry_id"],
            "title": item["title"],
            "date": item["date"],
            "excerpt": item["excerpt"],
            "similarity_score": item["similarity_score"],
        }
        for item in scored[:limit]
    ]
    return jsonify({"results": results})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat with journal context (global or entry-specific)."""
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    mode = data.get("mode", "global")
    entry_id = data.get("entry_id")
    messages = data.get("messages", [])

    if not query:
        return jsonify({"error": "query is required"}), 400

    if not status.ollama:
        return jsonify({
            "error": "AI chat is currently unavailable.",
            "details": status.ollama_message,
            "recoverable": True,
        }), 503

    from utils.ai import _get_prompt

    context_blocks = []
    if mode == "entry" and entry_id:
        entry = get_entry(entry_id)
        if not entry:
            return jsonify({"error": "Entry not found"}), 404
        context_blocks.append(f"Entry title: {entry.get('summary') or 'Untitled'}")
        context_blocks.append(f"Entry content: {entry.get('content', '')[:2000]}")
        persona = _get_prompt("chat_persona_entry")
    else:
        results = search_semantic(query, n_results=5)
        for hit in results:
            entry = get_entry(hit.get("entry_id"))
            if not entry:
                continue
            title = entry.get("summary") or entry.get("content", "")[:60]
            snippet = _entry_summary_snippet(entry, max_len=260)
            context_blocks.append(f"Title: {title}\nSnippet: {snippet}")
        persona = _get_prompt("chat_persona_global")

    history_lines = []
    for msg in messages[-10:]:
        role = msg.get("role")
        content = msg.get("content")
        if not content:
            continue
        prefix = "User" if role == "user" else "Assistant"
        history_lines.append(f"{prefix}: {content}")

    prompt_parts = [
        "Context:",
        "\n\n".join(context_blocks) if context_blocks else "No relevant context found.",
        "Conversation:",
        "\n".join(history_lines),
        f"User: {query}",
        "Assistant:",
    ]

    system_prompt = (
        persona
        + " Use only the provided journal context. If context is missing, say so."
    )

    from utils.ai import chat_with_ollama
    reply = chat_with_ollama("\n".join(prompt_parts), system_prompt=system_prompt)
    if not isinstance(reply, str):
        reply = str(reply or "")
    if reply.startswith("[Error"):
        return jsonify({"error": reply.strip("[]")}), 503
    return jsonify({"reply": reply})


@app.route("/api/memory/similar", methods=["POST"])
def api_memory_similar():
    """Return past entries similar to the current draft."""
    if get_setting("past_memories_enabled", "true") != "true":
        return jsonify({"similar_entries": []})
    data = request.get_json() or {}
    current_text = data.get("current_text", "").strip()
    exclude_recent_days = int(data.get("exclude_recent_days", 7))
    if not current_text:
        return jsonify({"similar_entries": []})

    matches = find_similar_entries(
        current_text,
        n_results=5,
        exclude_entry_ids=None,
        exclude_recent_days=exclude_recent_days,
    )

    similar_entries = []
    for match in matches:
        entry = get_entry(match.get("entry_id"))
        if not entry:
            continue
        title = entry.get("summary") or entry.get("content", "")[:60].strip()
        excerpt_source = entry.get("content", "")
        excerpt = excerpt_source[:200] + ("..." if len(excerpt_source) > 200 else "")
        similar_entries.append({
            "entry_id": entry.get("id"),
            "title": title or "Untitled",
            "date": entry.get("created_at"),
            "excerpt": excerpt,
            "similarity_score": match.get("similarity_score", 0),
        })

    return jsonify({"similar_entries": similar_entries})


@app.route("/api/entries/<entry_id>")
def api_entry(entry_id):
    """Fetch a single entry for modal display."""
    entry = get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"entry": entry})


@app.route("/api/prompts/personalized")
def api_personalized_prompts():
    """Generate personalized prompts using embedding-derived topics."""
    records = get_all_entry_embeddings()
    entry_count = get_entry_count()
    if not records or entry_count < 3:
        return jsonify({"error": "Not enough journal history for personalized prompts."}), 400

    clusters = _cluster_embeddings(records)

    def cluster_label(cluster):
        entry_id = cluster["entries"][0].get("entry_id") if cluster.get("entries") else None
        if not entry_id:
            return "past reflections"
        entry = get_entry(entry_id)
        if not entry:
            return "past reflections"
        if entry.get("tags"):
            return entry["tags"][0]
        if entry.get("summary"):
            return entry["summary"][:80]
        return entry.get("content", "")[:80].strip() or "past reflections"

    under_explored = []
    for cluster in sorted(clusters, key=lambda c: c["count"]):
        if cluster["count"] <= 2:
            under_explored.append(cluster_label(cluster))
        if len(under_explored) >= 3:
            break

    revisit_candidates = []
    for cluster in clusters:
        dates = []
        for entry in cluster.get("entries", []):
            meta_date = entry.get("metadata", {}).get("date")
            parsed = _parse_date(meta_date)
            if parsed:
                dates.append(parsed)
        if not dates:
            continue
        latest = max(dates)
        if (datetime.now() - latest).days >= 90:
            revisit_candidates.append((latest, cluster_label(cluster)))

    revisit_candidates.sort(key=lambda item: item[0])
    revisit_topics = [label for _, label in revisit_candidates[:3]]

    recent_cutoff = datetime.now().timestamp() - (30 * 24 * 60 * 60)
    recent_topics = []
    for rec in records:
        meta_date = rec.get("metadata", {}).get("date")
        parsed = _parse_date(meta_date)
        if not parsed or parsed.timestamp() < recent_cutoff:
            continue
        tags = rec.get("metadata", {}).get("tags", "")
        if tags:
            for tag in str(tags).split(","):
                tag = tag.strip()
                if tag and tag not in recent_topics:
                    recent_topics.append(tag)
        if len(recent_topics) >= 5:
            break

    prompt_result = generate_personalized_prompts_from_embeddings(
        under_explored_topics=under_explored,
        revisit_topics=revisit_topics,
        recent_topics=recent_topics,
        entry_count=entry_count,
    )

    if "error" in prompt_result:
        status_code = 503 if "Ollama" in prompt_result["error"] else 400
        return jsonify(prompt_result), status_code

    return jsonify(prompt_result)


@app.route("/api/entries/bulk-delete", methods=["POST"])
def api_bulk_delete():
    """Delete multiple journal entries at once."""
    data = request.get_json()
    entry_ids = data.get("entry_ids", [])
    if not entry_ids or not isinstance(entry_ids, list):
        return jsonify({"error": "entry_ids must be a non-empty list"}), 400
    entry_ids = entry_ids[:100]
    for eid in entry_ids:
        vector_delete(eid)
    deleted = bulk_delete_entries(entry_ids)
    return jsonify({"deleted": deleted})


@app.route("/api/entries/export", methods=["POST"])
def api_export_entries():
    """Export selected entries as JSON."""
    data = request.get_json()
    entry_ids = data.get("entry_ids", [])
    if not entry_ids or not isinstance(entry_ids, list):
        return jsonify({"error": "entry_ids must be a non-empty list"}), 400
    entries = get_entries_for_export(entry_ids[:100])
    return jsonify({"entries": entries})


@app.route("/api/data/export")
def api_data_export():
    """Export all entries as JSON or Markdown."""
    export_format = request.args.get("format", "json").lower()
    entries = get_all_entries_for_export()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if export_format in {"md", "markdown"}:
        markdown = _entries_to_markdown(entries)
        filename = f"journal_export_{timestamp}.md"
        return Response(
            markdown,
            mimetype="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    payload = {
        "entries": entries,
        "exported_at": datetime.now().isoformat(),
        "version": 1,
    }
    filename = f"journal_export_{timestamp}.json"
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/data/delete", methods=["POST"])
def api_delete_all_data():
    """Delete all journal entries and related data."""
    data = request.get_json() or {}
    confirm = str(data.get("confirm", ""))
    if confirm != "DELETE":
        return jsonify({"error": "Confirmation phrase did not match."}), 400
    delete_all_entries_data()
    return jsonify({"deleted": True})


@app.route("/api/settings/export")
def api_settings_export():
    """Export settings as JSON."""
    payload = _settings_export_payload()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"settings_export_{timestamp}.json"
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/settings/import", methods=["POST"])
def api_settings_import():
    """Import settings from JSON payload."""
    payload = None
    if request.is_json:
        payload = request.get_json() or {}
    elif "settings_file" in request.files:
        file = request.files["settings_file"]
        try:
            payload = json.loads(file.read().decode("utf-8"))
        except Exception:
            return jsonify({"error": "Invalid settings JSON file."}), 400
    if payload is None:
        return jsonify({"error": "No settings provided."}), 400

    settings_payload = payload.get("settings") if isinstance(payload, dict) else payload
    if not isinstance(settings_payload, dict):
        return jsonify({"error": "Settings payload must be an object."}), 400

    cleaned, errors = _validate_settings(settings_payload)
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    previous = _get_settings_with_defaults()
    set_settings_bulk(cleaned)
    restart_warnings = []
    for key, message in _restart_warning_keys().items():
        if previous.get(key) != cleaned.get(key):
            restart_warnings.append(message)
    return jsonify({"imported": True, "restart_warnings": restart_warnings})


@app.route("/api/services/refresh", methods=["POST"])
def api_refresh_services():
    """Re-check all service availability."""
    refresh_service_status()
    return jsonify({"services": status.summary(_current_language())})


# ---------------------------------------------------------------------------
# System Prompts API
# ---------------------------------------------------------------------------


@app.route("/api/system-prompts")
def api_list_system_prompts():
    """List all system prompts with metadata."""
    prompts = get_all_system_prompts()
    return jsonify({"prompts": prompts})


@app.route("/api/system-prompts/<key>")
def api_get_system_prompt(key):
    """Get a single system prompt by key."""
    prompt = get_system_prompt(key)
    if prompt is None:
        return jsonify({"error": f"Prompt '{key}' not found"}), 404
    return jsonify({"key": key, "prompt_text": prompt})


@app.route("/api/system-prompts/<key>", methods=["PUT", "POST"])
def api_update_system_prompt(key):
    """Update a system prompt's text."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    prompt_text = data.get("prompt_text")
    if not prompt_text or not prompt_text.strip():
        return jsonify({"error": "prompt_text is required"}), 400

    success = update_system_prompt(key, prompt_text.strip())
    if not success:
        return jsonify({"error": f"Prompt '{key}' not found"}), 404

    return jsonify({"success": True, "key": key})


@app.route("/api/system-prompts/<key>/reset", methods=["POST"])
def api_reset_system_prompt(key):
    """Reset a system prompt to its default from i18n."""
    from utils.ai import _get_prompt
    
    try:
        # Get default prompt from i18n system
        default_text = _get_prompt(key)
        if not default_text:
            return jsonify({"error": f"No default found for prompt '{key}'"}), 404

        success = update_system_prompt(key, default_text)
        if not success:
            return jsonify({"error": f"Prompt '{key}' not found in database"}), 404

        return jsonify({"success": True, "key": key, "prompt_text": default_text})
    except Exception as e:
        return jsonify({"error": f"Failed to reset prompt: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Tag Suggestion API
# ---------------------------------------------------------------------------


@app.route("/api/suggest-tags", methods=["POST"])
@rate_limit(max_requests=20, window_seconds=60)
def api_suggest_tags():
    """Smart tag suggestion with structured existing vs new tags and Baustellen links.
    
    Request body:
        - content: Entry text to analyze
        - existing_tags: Optional list of tags already applied
        - max_existing: Maximum existing tags to return (default 5)
        - max_new: Maximum new tags to return (default 2)
    
    Returns:
        JSON with structured suggestions including Baustelle connections
    """
    if not Config.TAG_ENABLED:
        return jsonify({"error": "Tag suggestions are disabled"}), 403
    
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint"}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400
    
    content = data.get("content", "").strip()
    existing_tags_raw = data.get("existing_tags", []) or []
    max_existing = min(int(data.get("max_existing", 5)), 8)
    max_new = min(int(data.get("max_new", 2)), 4)
    
    # Normalize existing tags
    existing_tags = [t.lower().strip().replace(' ', '-') for t in existing_tags_raw if t]
    
    # Validate content length
    if len(content) < Config.TAG_MIN_LENGTH:
        return jsonify({
            "error": f"Content too short (minimum {Config.TAG_MIN_LENGTH} characters)",
            "existing": [],
            "new": [],
            "confidence": 0.0
        }), 400
    
    # Import helpers
    from database.db import (
        get_user_tags_with_frequency, get_tag_cooccurrences,
        find_baustellen_by_tags, get_all_tag_defs, resolve_tag_alias,
        get_similar_entries_by_tags
    )
    
    suggestions = {
        "existing": [],
        "new": [],
        "confidence": 0.0,
        "fallback": False,
        "baustellen_matches": []
    }
    
    # Check Ollama availability
    if not status.ollama:
        suggestions["fallback"] = True
        suggestions["message"] = "AI unavailable - showing your popular tags"
        
        # Suggest from user's historical tags
        popular_tags = get_user_tags_with_frequency(limit=15)
        for tag_data in popular_tags:
            tag = tag_data["tag_name"]
            if tag not in existing_tags:
                suggestions["existing"].append({
                    "tag": tag,
                    "score": min(0.9, 0.5 + (tag_data["count"] / 10)),
                    "reason": f"Used {tag_data['count']} times",
                    "type": "existing"
                })
                if len(suggestions["existing"]) >= max_existing:
                    break
        
        suggestions["confidence"] = 0.5
        return jsonify(suggestions)
    
    # Stage 1: Get AI-extracted tags (potential new tags)
    ai_result = suggest_tags(content, max_tags=10)
    print(f"[TagSuggest] AI result: {ai_result}")

    ai_error = ai_result.get("error")
    if ai_error:
        print(f"[TagSuggest] AI error: {ai_error}")

    ai_tags_raw = ai_result.get("suggested_tags", []) if not ai_error else []
    ai_tags = [str(tag) for tag in ai_tags_raw] if isinstance(ai_tags_raw, list) else []
    print(f"[TagSuggest] AI tags extracted: {ai_tags}")

    # Stage 2: Get existing tags from user's history
    user_tags = get_user_tags_with_frequency(days=90, limit=30)
    user_tag_names = {t["tag_name"] for t in user_tags}
    print(f"[TagSuggest] User tags from history: {user_tag_names}")
    
    # Stage 3: Find co-occurring tags with existing entry tags
    if existing_tags:
        cooccurrences = get_tag_cooccurrences(min_cooccurrence=1, limit=10)
        cooccurring = [c for c in cooccurrences if c["tag1"] in existing_tags or c["tag2"] in existing_tags]
    else:
        cooccurring = []
    
    # Stage 4: Classify AI tags as existing or new
    ai_existing = []
    ai_new = []
    
    for tag in ai_tags:
        canonical = resolve_tag_alias(tag)
        if canonical in existing_tags:
            continue
        
        if canonical in user_tag_names:
            # Find frequency
            freq_data = next((t for t in user_tags if t["tag_name"] == canonical), None)
            count = freq_data["count"] if freq_data else 1
            ai_existing.append({
                "tag": canonical,
                "score": min(0.95, 0.7 + (count / 20)),
                "reason": f"You've used this {count} times",
                "type": "existing"
            })
        else:
            # Check if similar to existing tag
            similar_to = _find_similar_tag(canonical, user_tag_names)
            if similar_to:
                ai_existing.append({
                    "tag": similar_to,
                    "score": 0.75,
                    "reason": f"Similar to '{canonical}'",
                    "type": "existing",
                    "alias_for": canonical
                })
            else:
                ai_new.append({
                    "tag": canonical,
                    "score": 0.6,
                    "reason": "AI suggested",
                    "type": "new"
                })
    
    # Stage 5: Add popular tags that co-occur with existing tags
    for cooc in cooccurring:
        if cooc["tag1"] in existing_tags:
            related_tag = cooc["tag2"]
        else:
            related_tag = cooc["tag1"]
        
        if related_tag not in existing_tags and not any(s["tag"] == related_tag for s in suggestions["existing"]):
            suggestions["existing"].append({
                "tag": related_tag,
                "score": min(0.85, 0.6 + (cooc["co_occurrence"] / 5)),
                "reason": f"Often used with your tags",
                "type": "existing"
            })
    
    # Stage 6: Sort and limit
    suggestions["existing"].extend(ai_existing)
    suggestions["existing"].sort(key=lambda x: x["score"], reverse=True)
    suggestions["existing"] = suggestions["existing"][:max_existing]
    
    suggestions["new"] = ai_new[:max_new]
    
    # Stage 7: Find Baustellen matches
    all_suggested_tags = [s["tag"] for s in suggestions["existing"]] + [s["tag"] for s in suggestions["new"]]
    if all_suggested_tags:
        baustellen = find_baustellen_by_tags(all_suggested_tags, min_match=1)
        suggestions["baustellen_matches"] = [
            {
                "id": b["id"],
                "headline": b["headline"],
                "slug": b["slug"],
                "status": b["status"],
                "urgency": b["urgency"],
                "match_count": b["match_count"]
            }
            for b in baustellen[:3]
        ]
    
    # Calculate overall confidence
    if suggestions["existing"] or suggestions["new"]:
        max_score = max(
            [s["score"] for s in suggestions["existing"]] +
            [s["score"] for s in suggestions["new"]] +
            [0.3]
        )
        suggestions["confidence"] = round(max_score, 2)

    print(f"[TagSuggest] Final response: existing={len(suggestions['existing'])}, new={len(suggestions['new'])}, baustellen={len(suggestions['baustellen_matches'])}")
    return jsonify(suggestions)


def _find_similar_tag(tag_name, existing_tags, threshold=0.8):
    """Find if tag_name is similar to any existing tag using simple string similarity."""
    import difflib
    
    matches = difflib.get_close_matches(tag_name, existing_tags, n=1, cutoff=threshold)
    return matches[0] if matches else None


@app.route("/api/tags/popular")
def api_popular_tags():
    """Get user's most popular tags with frequency counts."""
    from database.db import get_user_tags_with_frequency
    
    days = request.args.get("days", 90, type=int)
    limit = min(request.args.get("limit", 20, type=int), 50)
    
    tags = get_user_tags_with_frequency(days=days, limit=limit)
    return jsonify({"tags": tags})


# ---------------------------------------------------------------------------
# Baustellen API (Curated Ongoing Concerns)
# ---------------------------------------------------------------------------


@app.route("/api/baustellen", methods=["GET"])
def api_list_baustellen():
    """List all Baustellen, optionally filtered by status."""
    from database.db import get_all_baustellen
    
    status_filter = request.args.get("status")
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    order_by = request.args.get("order_by", "pinned_first")
    
    baustellen = get_all_baustellen(
        status=status_filter,
        include_inactive=include_inactive,
        order_by=order_by
    )
    
    return jsonify({"baustellen": baustellen, "count": len(baustellen)})


@app.route("/api/baustellen/<int:baustelle_id>", methods=["GET"])
def api_get_baustelle(baustelle_id):
    """Get a single Baustelle with its tags and linked entries."""
    from database.db import get_baustelle, get_entries_for_baustelle
    
    baustelle = get_baustelle(baustelle_id)
    if not baustelle:
        return jsonify({"error": "Baustelle not found"}), 404
    
    # Get linked entries
    entries = get_entries_for_baustelle(baustelle_id, limit=10)
    baustelle["recent_entries"] = entries
    
    return jsonify(baustelle)


@app.route("/api/baustellen", methods=["POST"])
def api_create_baustelle():
    """Create a new Baustelle (manual or from AI analysis)."""
    from database.db import create_baustelle, link_tag_to_baustelle
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400
    
    headline = data.get("headline", "").strip()
    if not headline:
        return jsonify({"error": "headline is required"}), 400
    
    core_problem = data.get("core_problem", "").strip() or None
    recent_development = data.get("recent_development", "").strip() or None
    status = data.get("status", "stable")
    urgency = min(5, max(1, int(data.get("urgency", 3))))
    is_pinned = 1 if data.get("is_pinned", False) else 0
    
    try:
        baustelle_id = create_baustelle(
            headline=headline,
            core_problem=core_problem,
            recent_development=recent_development,
            status=status,
            urgency=urgency,
            is_pinned=is_pinned,
            is_auto_generated=0  # Manual creation
        )
        
        # Link tags if provided
        tags = data.get("tags", [])
        for tag in tags:
            link_tag_to_baustelle(baustelle_id, tag, weight=1.0, is_primary=(tag == tags[0] if tags else False))
        
        return jsonify({"id": baustelle_id, "success": True}), 201
    except Exception as e:
        log.error("Failed to create Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/<int:baustelle_id>", methods=["PUT"])
def api_update_baustelle(baustelle_id):
    """Update a Baustelle."""
    from database.db import update_baustelle, get_baustelle
    
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400
    
    updates = {}
    allowed_fields = ["headline", "core_problem", "recent_development", "status", "urgency", "is_pinned"]
    
    for field in allowed_fields:
        if field in data:
            if field == "is_pinned":
                updates[field] = 1 if data[field] else 0
            elif field == "urgency":
                updates[field] = min(5, max(1, int(data[field])))
            else:
                updates[field] = data[field]
    
    try:
        success = update_baustelle(baustelle_id, **updates)
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to update Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/<int:baustelle_id>/pin", methods=["POST"])
def api_pin_baustelle(baustelle_id):
    """Pin or unpin a Baustelle."""
    from database.db import update_baustelle, get_baustelle
    
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    data = request.get_json() or {}
    is_pinned = 1 if data.get("pinned", True) else 0
    
    try:
        update_baustelle(baustelle_id, is_pinned=is_pinned)
        return jsonify({"success": True, "pinned": bool(is_pinned)})
    except Exception as e:
        log.error("Failed to pin Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/<int:baustelle_id>", methods=["DELETE"])
def api_delete_baustelle(baustelle_id):
    """Delete a Baustelle."""
    from database.db import delete_baustelle, get_baustelle
    
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    try:
        success = delete_baustelle(baustelle_id)
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to delete Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/<int:baustelle_id>/tags", methods=["POST"])
def api_add_tag_to_baustelle(baustelle_id):
    """Link a tag to a Baustelle."""
    from database.db import link_tag_to_baustelle, get_baustelle
    
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    data = request.get_json()
    if not data or not data.get("tag"):
        return jsonify({"error": "tag is required"}), 400
    
    tag = data["tag"]
    weight = data.get("weight", 1.0)
    is_primary = data.get("is_primary", False)
    
    try:
        success = link_tag_to_baustelle(baustelle_id, tag, weight=weight, is_primary=is_primary)
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to link tag to Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/<int:baustelle_id>/tags/<tag_name>", methods=["DELETE"])
def api_remove_tag_from_baustelle(baustelle_id, tag_name):
    """Remove a tag link from a Baustelle."""
    from database.db import unlink_tag_from_baustelle, get_baustelle
    
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    try:
        success = unlink_tag_from_baustelle(baustelle_id, tag_name)
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to unlink tag from Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/entries/<entry_id>/baustellen", methods=["GET"])
def api_get_entry_baustellen(entry_id):
    """Get Baustellen linked to an entry."""
    from database.db import get_baustellen_for_entry
    
    baustellen = get_baustellen_for_entry(entry_id)
    return jsonify({"baustellen": baustellen})


@app.route("/api/entries/<entry_id>/baustellen", methods=["POST"])
def api_link_entry_to_baustelle(entry_id):
    """Manually link an entry to a Baustelle."""
    from database.db import link_entry_to_baustelle, get_baustelle
    
    data = request.get_json()
    if not data or not data.get("baustelle_id"):
        return jsonify({"error": "baustelle_id is required"}), 400
    
    baustelle_id = data["baustelle_id"]
    
    # Verify Baustelle exists
    if not get_baustelle(baustelle_id):
        return jsonify({"error": "Baustelle not found"}), 404
    
    confidence = data.get("confidence", 0.8)
    
    try:
        success = link_entry_to_baustelle(entry_id, baustelle_id, confidence=confidence, link_source='user')
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to link entry to Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/entries/<entry_id>/baustellen/<int:baustelle_id>", methods=["DELETE"])
def api_unlink_entry_from_baustelle(entry_id, baustelle_id):
    """Remove an entry link from a Baustelle."""
    from database.db import unlink_entry_from_baustelle
    
    try:
        success = unlink_entry_from_baustelle(entry_id, baustelle_id)
        return jsonify({"success": success})
    except Exception as e:
        log.error("Failed to unlink entry from Baustelle: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/baustellen/analyze", methods=["POST"])
def api_analyze_baustellen():
    """Trigger AI analysis to generate/update Baustellen from recent entries."""
    from database.db import (
        get_filtered_entries, create_baustelle, link_tag_to_baustelle,
        link_entry_to_baustelle, get_all_baustellen, update_baustelle
    )
    
    data = request.get_json() or {}
    range_days = data.get("range_days", 60)
    auto_create = data.get("auto_create", True)
    
    # Fetch entries for analysis
    date_from, date_to = _range_to_dates(f"{range_days}d")
    entries = get_filtered_entries(
        limit=100,
        offset=0,
        sort_by="created_at",
        sort_dir="DESC",
        date_from=date_from,
        date_to=date_to,
    )
    
    # Prepare entry data
    entry_data = []
    for e in entries:
        if e.get("content"):
            entry_data.append({
                "id": e.get("id"),
                "date": e.get("created_at"),
                "content": _entry_summary_snippet(e, max_len=200),
                "tags": e.get("tags", []),
                "emotions": [em.get("emotion") for em in e.get("emotions", [])]
            })
    
    if not entry_data:
        return jsonify({"error": "No entries to analyze"}), 400
    
    # Generate Baustellen analysis
    # Check cache first to avoid duplicate generation on repeated clicks
    current_hash = get_dataset_hash(date_from, date_to)
    cache_key = f"baustellen_analysis_{range_days}"
    cached_raw = get_setting(cache_key)
    
    result = None
    is_cached = False
    
    if cached_raw:
        try:
            cached_obj = json.loads(cached_raw)
            if cached_obj.get("hash") == current_hash:
                result = cached_obj.get("data")
                is_cached = True
        except (ValueError, TypeError):
            pass
            
    if not result:
        result = generate_baustellen_analysis(entry_data)
        
        # Cache successful result
        if "error" not in result:
            try:
                cache_payload = json.dumps({"hash": current_hash, "data": result})
                set_setting(cache_key, cache_payload)
            except Exception as e:
                log.warning("Failed to cache Baustellen analysis: %s", e)
    
    if "error" in result:
        error_text = str(result.get("error", ""))
        status_code = 503 if "not available" in error_text.lower() else 400
        return jsonify(result), status_code
    
    baustellen_data_raw = result.get("baustellen", [])
    baustellen_data = [b for b in baustellen_data_raw if isinstance(b, dict)] if isinstance(baustellen_data_raw, list) else []
    
    # If cached, we can skip the DB update logic to prevent "drift" 
    # and just return the data with a flag
    if is_cached:
        return jsonify({
            "baustellen": baustellen_data,
            "count": len(baustellen_data),
            "cached": True,
            "message": _t("insights.issues.cached")
        })
    
    if auto_create and status.ollama:
        # Get existing Baustellen to avoid duplicates
        existing = get_all_baustellen(include_inactive=True)
        existing_headlines = {b["headline"].lower() for b in existing}
        
        created = []
        updated = []
        
        for b_data in baustellen_data:
            headline = b_data.get("headline", "")
            headline_lower = headline.lower()
            
            # Check for similar existing Baustelle
            similar = _find_similar_baustelle(headline_lower, existing)
            
            if similar:
                # Update existing
                update_baustelle(
                    similar["id"],
                    core_problem=b_data.get("core_problem"),
                    recent_development=b_data.get("recent_development"),
                    status=b_data.get("status", "stable"),
                    urgency=b_data.get("urgency", 3)
                )
                updated.append({"id": similar["id"], "headline": headline})
            elif headline_lower not in existing_headlines:
                # Create new
                baustelle_id = create_baustelle(
                    headline=headline,
                    core_problem=b_data.get("core_problem"),
                    recent_development=b_data.get("recent_development"),
                    status=b_data.get("status", "stable"),
                    urgency=b_data.get("urgency", 3),
                    is_auto_generated=1
                )
                
                # Link tags from the analysis (if any)
                # Note: Baustellen analysis doesn't currently return tags,
                # but we could enhance the AI prompt to suggest related tags
                
                created.append({"id": baustelle_id, "headline": headline})
        
        return jsonify({
            "baustellen": baustellen_data,
            "created": created,
            "updated": updated,
            "count": len(baustellen_data)
        })
    
    return jsonify({
        "baustellen": baustellen_data,
        "count": len(baustellen_data),
        "auto_create": auto_create
    })


def _find_similar_baustelle(headline, existing_baustellen, threshold=0.85):
    """Find if a Baustelle with similar headline already exists."""
    import difflib
    
    for b in existing_baustellen:
        similarity = difflib.SequenceMatcher(None, headline, b["headline"].lower()).ratio()
        if similarity >= threshold:
            return b
    return None


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


def _get_or_generate_daily_question():
    """Get today's daily question, generating a new one if needed.

    Returns:
        dict with keys: question, is_new, is_answered, date
        or dict with key: error
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if we already have a question for today
    existing = get_daily_question(today)
    if existing:
        return {
            "question": existing["question_text"],
            "is_new": False,
            "is_answered": existing["is_answered"],
            "date": today,
        }

    # Check if there are previous entries to personalize from
    if not has_previous_entries():
        return {
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
            "no_entries": True,
            "message": _t("daily_question.start_journaling"),
        }

    # Check if Ollama is available
    if not status.ollama:
        return {
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
            "message": _t("daily_question.ai_offline"),
        }

    # Get recent entry summaries to generate a personalized question
    recent_entries = get_all_entries(limit=10)
    recent_summaries = [
        _entry_summary_snippet(e, max_len=200)
        for e in recent_entries
        if e.get("content")
    ]

    if not recent_summaries:
        return {
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
        }

    # Generate a new question
    result = generate_daily_question(recent_summaries)
    if "error" in result:
        return {
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
            "message": result["error"],
        }

    # Save the generated question
    question_text = result.get("question", _t("daily_question.default"))
    create_daily_question(today, question_text)

    return {
        "question": question_text,
        "is_new": True,
        "is_answered": False,
        "date": today,
    }


@app.route("/api/dashboard/stats")
def api_dashboard_stats():
    """Get dashboard statistics including streak, entry count, daily question, and personalized prompts."""
    streak = get_streak()
    entry_count = get_entry_count()
    total_words = get_total_words()
    top_emotion_data = get_top_emotion()
    daily_question = _get_or_generate_daily_question()
    
    # Generate personalized prompts for "Explore More" section
    personalized_prompts = None
    if entry_count >= 3:
        try:
            records = get_all_entry_embeddings()
            clusters = _cluster_embeddings(records)
            
            def cluster_label(cluster):
                entry_id = cluster["entries"][0].get("entry_id") if cluster.get("entries") else None
                if not entry_id:
                    return "past reflections"
                entry = get_entry(entry_id)
                if not entry:
                    return "past reflections"
                if entry.get("tags"):
                    return entry["tags"][0]
                if entry.get("summary"):
                    return entry["summary"][:80]
                return entry.get("content", "")[:80].strip() or "past reflections"
            
            # Under-explored topics (clusters with <=2 entries)
            under_explored = []
            for cluster in sorted(clusters, key=lambda c: c["count"]):
                if cluster["count"] <= 2:
                    under_explored.append(cluster_label(cluster))
                if len(under_explored) >= 3:
                    break
            
            # Revisit topics (not touched in 90+ days)
            revisit_candidates = []
            for cluster in clusters:
                dates = []
                for entry in cluster.get("entries", []):
                    meta_date = entry.get("metadata", {}).get("date")
                    parsed = _parse_date(meta_date)
                    if parsed:
                        dates.append(parsed)
                if not dates:
                    continue
                latest = max(dates)
                if (datetime.now() - latest).days >= 90:
                    revisit_candidates.append((latest, cluster_label(cluster)))
            revisit_candidates.sort(key=lambda item: item[0])
            revisit_topics = [label for _, label in revisit_candidates[:3]]
            
            # Recent topics for context
            recent_cutoff = datetime.now().timestamp() - (30 * 24 * 60 * 60)
            recent_topics = []
            for rec in records:
                meta_date = rec.get("metadata", {}).get("date")
                parsed = _parse_date(meta_date)
                if not parsed or parsed.timestamp() < recent_cutoff:
                    continue
                tags = rec.get("metadata", {}).get("tags", "")
                if tags:
                    for tag in str(tags).split(","):
                        tag = tag.strip()
                        if tag and tag not in recent_topics:
                            recent_topics.append(tag)
                if len(recent_topics) >= 5:
                    break
            
            prompt_result = generate_personalized_prompts_from_embeddings(
                under_explored_topics=under_explored,
                revisit_topics=revisit_topics,
                recent_topics=recent_topics,
                entry_count=entry_count,
            )
            
            if "prompts" in prompt_result:
                personalized_prompts = prompt_result["prompts"]
        except Exception as e:
            # Silently fail - this is an enhancement, not critical
            pass

    return jsonify({
        "streak": streak,
        "entry_count": entry_count,
        "total_words": total_words,
        "top_emotion": top_emotion_data.get("emotion") if top_emotion_data else None,
        "daily_question": daily_question,
        "personalized_prompts": personalized_prompts,
    })


@app.route("/api/dashboard/emotions")
def api_dashboard_emotions():
    """Get emotion data for dashboard visualization."""
    range_days = _parse_range_days(request.args.get("range"), default=30)
    timeline = get_emotion_timeline(range_days=range_days)
    totals = get_emotion_totals()

    return jsonify({
        "range_days": range_days,
        "timeline": timeline,
        "totals": totals,
    })


@app.route("/api/calendar")
def api_calendar():
    """Return entry counts per day for a given month."""
    now = datetime.now()
    try:
        year = int(request.args.get("year", now.year))
        month = int(request.args.get("month", now.month))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid year or month"}), 400

    if month < 1 or month > 12:
        return jsonify({"error": "Month must be between 1 and 12"}), 400

    import sqlite3
    from config import Config as _Cfg

    date_prefix = f"{year:04d}-{month:02d}"
    conn = sqlite3.connect(_Cfg.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT DATE(created_at) as day, COUNT(*) as count "
        "FROM entries WHERE DATE(created_at) LIKE ? || '%' "
        "GROUP BY DATE(created_at)",
        (date_prefix,),
    ).fetchall()
    conn.close()

    days = [{"date": row["day"], "count": row["count"]} for row in rows]
    return jsonify({"year": year, "month": month, "days": days})


@app.route("/api/daily-question/answered", methods=["POST"])
def api_mark_daily_question_answered():
    """Mark today's daily question as answered."""
    data = request.get_json() or {}
    date = data.get("date")  # Optional: defaults to today
    answered = data.get("answered", True)

    mark_daily_question_answered(date=date, answered=answered)

    return jsonify({"success": True})


@app.route("/api/daily-question/new", methods=["POST"])
def api_new_daily_question():
    """Generate a new daily question, replacing the existing one for today."""
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403

    if not status.ollama:
        return jsonify({
            "error": _t("ai.unavailable"),
            "details": status.ollama_message,
            "recoverable": True,
        }), 503

    today = datetime.now().strftime("%Y-%m-%d")

    # Check if there are previous entries to personalize from
    if not has_previous_entries():
        return jsonify({
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
            "no_entries": True,
            "message": _t("daily_question.start_journaling"),
        })

    # Get recent entry summaries to generate a personalized question
    recent_entries = get_all_entries(limit=10)
    recent_summaries = [
        _entry_summary_snippet(e, max_len=200)
        for e in recent_entries
        if e.get("content")
    ]

    if not recent_summaries:
        return jsonify({
            "question": _t("daily_question.default"),
            "is_new": False,
            "is_answered": False,
            "date": today,
            "fallback": True,
        })

    # Generate a new question
    result = generate_daily_question(recent_summaries)
    if "error" in result:
        return jsonify({
            "error": result["error"],
            "recoverable": True,
        }), 503

    # Replace the existing question with the new one
    question_text = result.get("question", _t("daily_question.default"))
    replace_daily_question(today, question_text)

    return jsonify({
        "question": question_text,
        "is_new": True,
        "is_answered": False,
        "date": today,
    })


@app.route("/api/generate/deeper-questions", methods=["POST"])
def api_deeper_questions():
    """Generate reflective follow-up questions for journal content."""
    if get_setting("go_deeper_enabled", "true") != "true":
        return jsonify({"error": "Go Deeper suggestions are disabled in settings."}), 403
    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403
    data = request.get_json()
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    previous_questions = data.get("previous_questions", [])

    if not isinstance(previous_questions, list):
        previous_questions = []

    result = generate_deeper_questions(text, previous_questions)

    if "error" in result:
        status_code = 503 if "not available" in result["error"].lower() else 400
        return jsonify(result), status_code

    return jsonify(result)


@app.route("/api/analyze/entry", methods=["POST"])
@rate_limit(max_requests=5, window_seconds=60)
def api_analyze_entry():
    """Comprehensive AI analysis of a journal entry with SSE progress updates.

    Input: {entry_id: "uuid"}
    Output: Server-Sent Events stream with progress and final results
    """
    data = request.get_json()
    entry_id = data.get("entry_id")

    if not entry_id:
        return jsonify({"error": "entry_id is required"}), 400

    entry = get_entry(entry_id)
    if not entry:
        return jsonify({"error": "Entry not found"}), 404

    if _local_only_block(Config.OLLAMA_BASE_URL):
        return jsonify({"error": "Local-only mode blocks external Ollama endpoint."}), 403

    content = entry["content"]
    emotion_enabled = get_setting("emotion_analysis_enabled", "true") == "true"
    artwork_enabled = get_setting("artwork_enabled", "true") == "true"

    def generate():
        start_time = time.time()
        result = {
            "entry_id": entry_id,
            "summary": None,
            "title": None,
            "themes": [],
            "emotions": [],
            "patterns": None,
            "artwork_prompt": None,
        }

        # Step 1: Detect Emotions
        if not emotion_enabled:
            yield f"data: {json.dumps({'step': 1, 'status': 'skipped', 'message': 'Emotion analysis disabled'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 1, 'status': 'running', 'message': 'Analyzing emotions...'})}\n\n"
            emotions_result = detect_emotions(content)
            if "error" in emotions_result:
                yield f"data: {json.dumps({'step': 1, 'status': 'error', 'message': emotions_result['error']})}\n\n"
                result["emotions"] = []
            else:
                raw_emotions = emotions_result.get("emotions", [])
                result["emotions"] = [
                    e for e in raw_emotions
                    if isinstance(e, dict) and e.get("emotion")
                ] if isinstance(raw_emotions, list) else []
                # Save emotions to database
                db_emotions = [
                    {
                        "emotion": e.get("emotion"),
                        "intensity": e.get("intensity", "medium"),
                        "frequency": e.get("frequency", 0.5),
                    }
                    for e in result["emotions"]
                ]
                set_emotions(entry_id, db_emotions)
                yield f"data: {json.dumps({'step': 1, 'status': 'complete', 'message': 'Emotions analyzed', 'data': result['emotions']})}\n\n"

        # Step 2: Generate Summary
        yield f"data: {json.dumps({'step': 2, 'status': 'running', 'message': 'Generating summary...'})}\n\n"
        summary_result = generate_summary_and_title(content)
        if "error" in summary_result:
            yield f"data: {json.dumps({'step': 2, 'status': 'error', 'message': summary_result['error']})}\n\n"
        else:
            result["summary"] = summary_result.get("summary", "")
            result["title"] = summary_result.get("title", "")
            result["themes"] = summary_result.get("themes", [])
            # Save summary to database
            update_entry(entry_id, summary=result["summary"])
            yield f"data: {json.dumps({'step': 2, 'status': 'complete', 'message': 'Summary generated', 'data': {'title': result['title'], 'summary': result['summary'], 'themes': result['themes']}})}\n\n"

        # Step 3: Identify Patterns
        yield f"data: {json.dumps({'step': 3, 'status': 'running', 'message': 'Identifying patterns...'})}\n\n"
        patterns_result = identify_patterns(content, themes=result["themes"])
        if "error" in patterns_result:
            yield f"data: {json.dumps({'step': 3, 'status': 'error', 'message': patterns_result['error']})}\n\n"
        else:
            result["patterns"] = patterns_result
            yield f"data: {json.dumps({'step': 3, 'status': 'complete', 'message': 'Patterns identified', 'data': patterns_result})}\n\n"

        # Step 4: Generate Artwork
        if not artwork_enabled:
            yield f"data: {json.dumps({'step': 4, 'status': 'skipped', 'message': 'Artwork generation disabled'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 4, 'status': 'running', 'message': 'Generating artwork...'})}\n\n"
            sentiment = result["patterns"].get("sentiment_trend", "neutral") if result["patterns"] else "neutral"
            
            # Get style from settings
            style = get_setting("sd_default_style", Config.SD_DEFAULT_STYLE)
            style = _normalize_style(style)
            if style not in ARTWORK_STYLES:
                style = Config.SD_DEFAULT_STYLE
            
            # Build themes from tags or use defaults
            themes = result["themes"] if result["themes"] else ["reflection"]
            emotions = result["emotions"] if result["emotions"] else []
            
            # Build artwork prompt
            prompt = build_artwork_prompt(style, themes=themes, emotions=emotions, sentiment=sentiment)
            
            # Generate the actual image
            start_time = time.time()
            filename_base = f"artwork_{entry_id}_{int(start_time)}"
            artwork_url = None
            model_used = "none"
            
            try:
                image_result = generate_image(
                    prompt,
                    style=style,
                    emotions=emotions,
                    themes=themes,
                    entry_id=entry_id
                )
                
                if image_result:
                    model_used = image_result.get("source", "unknown")
                    
                    if image_result["type"] == "bytes":
                        # ComfyUI or algorithmic art returns bytes
                        artwork_url = save_bytes_image(image_result["data"], f"{filename_base}.png")
                    elif image_result["type"] == "base64":
                        # Stable Diffusion WebUI returns base64
                        artwork_url = save_image(image_result["data"], f"{filename_base}.png")
                
                if artwork_url:
                    # Update entry with artwork path and style
                    update_entry(entry_id, artwork_path=artwork_url, artwork_style=style)
                    result["artwork_path"] = artwork_url
                    result["artwork_style"] = style
                    generation_time = round(time.time() - start_time, 2)
                    yield f"data: {json.dumps({'step': 4, 'status': 'complete', 'message': 'Artwork generated', 'data': {'artwork_path': artwork_url, 'style': style, 'model_used': model_used, 'generation_time': generation_time}})}\n\n"
                else:
                    yield f"data: {json.dumps({'step': 4, 'status': 'error', 'message': 'Image generation failed - no image returned'})}\n\n"
            except Exception as e:
                log.error("Error generating artwork for entry %s: %s", entry_id, e)
                yield f"data: {json.dumps({'step': 4, 'status': 'error', 'message': f'Artwork generation failed: {str(e)}'})}\n\n"

        # Step 5: Generate AI Insights (uses the editable analyze_entry prompt)
        yield f"data: {json.dumps({'step': 5, 'status': 'running', 'message': 'Generating AI insights...'})}\n\n"
        insights_result = analyze_entry(content)
        if not isinstance(insights_result, str):
            insights_result = str(insights_result or "")
        if insights_result.startswith("[Error"):
            yield f"data: {json.dumps({'step': 5, 'status': 'error', 'message': insights_result})}\n\n"
        else:
            # Save AI insights as summary for consistency with re-analyze
            update_entry(entry_id, summary=insights_result)
            yield f"data: {json.dumps({'step': 5, 'status': 'complete', 'message': 'AI insights generated', 'data': {'insights': insights_result[:200] + '...' if len(insights_result) > 200 else insights_result}})}\n\n"

        # Final result
        processing_time = round(time.time() - start_time, 2)
        result["processing_time"] = processing_time
        _reindex_entry(entry_id)
        yield f"data: {json.dumps({'step': 'done', 'status': 'complete', 'result': result})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------


@app.route("/status")
def system_status():
    """Comprehensive system status page."""
    settings = _get_settings_with_defaults()
    language = normalize_language(settings.get("ui_language") or Config.DEFAULT_LANGUAGE)
    diagnostics = get_detailed_status(language)
    # Return JSON if requested (for setup wizard)
    if request.args.get("format") == "json":
        return jsonify(diagnostics)
    return render_template("status.html", diagnostics=diagnostics)


@app.route("/api/status")
def api_status():
    """API endpoint for system diagnostics."""
    settings = _get_settings_with_defaults()
    language = normalize_language(settings.get("ui_language") or Config.DEFAULT_LANGUAGE)
    diagnostics = get_detailed_status(language)
    return jsonify(diagnostics)


@app.route("/api/database/health")
def api_database_health():
    """Check database health and return statistics."""
    integrity = check_database_integrity()
    stats = get_database_stats()

    return jsonify({
        "healthy": integrity.get("ok", False),
        "integrity_message": integrity.get("message"),
        "stats": stats,
    })


@app.route("/api/services/test", methods=["POST"])
def api_test_services():
    """Test all services with actual operations."""
    results = {}

    # Test Ollama
    if status.ollama:
        try:
            from utils.ai import chat_with_ollama
            response = chat_with_ollama("Say 'test successful' in exactly two words.")
            if not isinstance(response, str):
                response = str(response or "")
            results["ollama"] = {
                "success": "error" not in response.lower(),
                "message": response[:100] if response else "No response",
            }
        except Exception as e:
            results["ollama"] = {"success": False, "message": str(e)}
    else:
        results["ollama"] = {"success": False, "message": "Service not available"}

    # Test Whisper (just check import)
    try:
        import whisper
        results["whisper"] = {"success": True, "message": "Module available"}
    except ImportError:
        results["whisper"] = {"success": False, "message": "Module not installed"}

    # Test ChromaDB
    if status.chromadb:
        try:
            from models.vector_store import get_collection_stats
            stats = get_collection_stats()
            results["chromadb"] = {
                "success": True,
                "message": f"{stats.get('count', 0)} documents indexed",
            }
        except Exception as e:
            results["chromadb"] = {"success": False, "message": str(e)}
    else:
        results["chromadb"] = {"success": False, "message": "Service not available"}

    # Test Database
    try:
        count = get_entry_count()
        results["database"] = {"success": True, "message": f"{count} entries in database"}
    except Exception as e:
        results["database"] = {"success": False, "message": str(e)}

    return jsonify({"results": results})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(400)
def bad_request(e):
    """Handle bad request errors (malformed JSON, missing required fields)."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": str(e.description) if hasattr(e, 'description') else "Bad request",
            "status": 400,
        }), 400
    return render_template("404.html", error_message="Bad request"), 400


@app.errorhandler(404)
def page_not_found(e):
    """Handle not found errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": "Resource not found",
            "status": 404,
        }), 404
    return render_template("404.html"), 404


@app.errorhandler(413)
def request_entity_too_large(e):
    """Handle file too large errors."""
    max_size_mb = Config.MAX_CONTENT_LENGTH / (1024 * 1024)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": f"Request too large. Maximum size is {max_size_mb:.0f} MB.",
            "status": 413,
        }), 413
    return render_template("500.html", error_message=f"Upload too large (max {max_size_mb:.0f} MB)"), 413


@app.errorhandler(422)
def unprocessable_entity(e):
    """Handle validation errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": str(e.description) if hasattr(e, 'description') else "Validation error",
            "status": 422,
        }), 422
    return render_template("500.html", error_message="Validation error"), 422


@app.errorhandler(500)
def internal_error(e):
    """Handle internal server errors."""
    log.exception("Internal server error: %s", e)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": "An internal error occurred. Please try again.",
            "status": 500,
        }), 500
    return render_template("500.html"), 500


@app.errorhandler(503)
def service_unavailable(e):
    """Handle service unavailable errors (e.g., Ollama offline)."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": str(e.description) if hasattr(e, 'description') else "Service temporarily unavailable",
            "status": 503,
            "recoverable": True,
        }), 503
    return render_template("500.html", error_message="Service temporarily unavailable"), 503


@app.errorhandler(DatabaseError)
def handle_database_error(e):
    """Handle custom DatabaseError exceptions."""
    log.error("Database error: %s", e)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": e.message,
            "category": "database",
            "operation": e.operation,
            "recoverable": False,
        }), 500
    return render_template("500.html", error_message="A database error occurred"), 500


@app.errorhandler(ValidationError)
def handle_validation_error(e):
    """Handle custom ValidationError exceptions."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": e.user_message,
            "category": "validation",
            "field": e.field,
            "recoverable": True,
        }), 422
    return render_template("500.html", error_message=e.user_message), 422


@app.errorhandler(Exception)
def handle_generic_exception(e):
    """Catch-all handler for unexpected exceptions."""
    log.exception("Unhandled exception: %s", e)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": "An unexpected error occurred. Please try again.",
            "status": 500,
        }), 500
    return render_template("500.html"), 500


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------


@app.before_request
def log_request():
    """Log incoming requests for debugging."""
    if Config.DEBUG:
        log.debug(
            "Request: %s %s (Content-Length: %s)",
            request.method,
            request.path,
            request.content_length or 0,
        )


@app.after_request
def log_response(response):
    """Log response status for debugging."""
    if Config.DEBUG and response.status_code >= 400:
        log.warning(
            "Response: %s %s -> %s",
            request.method,
            request.path,
            response.status,
        )
    return response


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="PrismA Journal - Secure AI-powered journaling app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/app.py                    # Use default LLM provider from .env
  python app/app.py --ollama           # Force Ollama
  python app/app.py --lmstudio         # Force LM Studio
  python app/app.py --language en      # Use English
  python app/app.py --language de      # Use German (default)
        """
    )
    
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--ollama",
        action="store_const",
        const="ollama",
        dest="llm_provider",
        help="Use Ollama as LLM provider (overrides .env)"
    )
    llm_group.add_argument(
        "--lmstudio",
        action="store_const",
        const="lmstudio",
        dest="llm_provider",
        help="Use LM Studio as LLM provider (overrides .env)"
    )
    llm_group.add_argument(
        "--llm",
        choices=["ollama", "lmstudio"],
        dest="llm_provider",
        help="Specify LLM provider explicitly"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run the server on (default: 5000)"
    )
    
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--language",
        "--lang",
        choices=["en", "de"],
        dest="language",
        help="Set UI and AI response language: 'en' (English) or 'de' (German, default)"
    )
    
    args = parser.parse_args()
    
    # Override Config.LLM_PROVIDER if command-line argument provided
    if args.llm_provider:
        Config.LLM_PROVIDER = args.llm_provider.lower()
        print(f"[CLI Override] LLM Provider set to: {Config.LLM_PROVIDER}")
    
    # Override Config.DEFAULT_LANGUAGE if command-line argument provided
    if args.language:
        Config.DEFAULT_LANGUAGE = args.language.lower()
        print(f"[CLI Override] Language set to: {Config.DEFAULT_LANGUAGE}")
    
    init_services()
    init_db()

    # Always set ui_language to DEFAULT_LANGUAGE on startup (ensures German default).
    # CLI override takes precedence, otherwise defaults to German.
    set_setting("ui_language", normalize_language(Config.DEFAULT_LANGUAGE))

    effective_default_language = normalize_language(Config.DEFAULT_LANGUAGE)
    persisted_ui_language = normalize_language(
        get_setting("ui_language") or effective_default_language
    )
    print(
        "[Language] "
        f"DEFAULT_LANGUAGE={effective_default_language} "
        f"| ui_language={persisted_ui_language}"
    )
    # Apply data retention policy (delete old entries)
    from database.db import apply_data_retention
    retention_result = apply_data_retention()
    if retention_result.get("deleted_count", 0) > 0:
        print(f"Data retention: deleted {retention_result['deleted_count']} entries "
              f"(policy: {retention_result['retention_policy']})")
    
    # Print the URL before starting the server
    url = f"http://127.0.0.1:{args.port}" if args.host == "0.0.0.0" else f"http://{args.host}:{args.port}"
    print(f"\n{'='*60}")
    print(f"  PrismA Journal is running at: {url}")
    print(f"{'='*60}\n")
    
    app.run(debug=Config.DEBUG, host=args.host, port=args.port)
