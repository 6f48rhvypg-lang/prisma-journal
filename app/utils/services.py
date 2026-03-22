"""Service initialization and health checks.

Provides a central place to probe external dependencies (Ollama, Whisper,
ChromaDB, sentence-transformers, Stable Diffusion) and report which are
available.  The app continues in degraded mode when services are missing —
features that depend on an unavailable service are simply disabled at runtime.
"""

import logging
import sys
import os
import time
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import requests
from config import Config
from .i18n import translate as _t

# Optional import for system diagnostics
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service status registry
# ---------------------------------------------------------------------------


class ServiceStatus:
    """Tracks availability of each optional service."""

    def __init__(self):
        self.ollama: bool = False
        self.ollama_message: str = ""
        self.ollama_message_i18n: dict = {}
        self.lmstudio: bool = False
        self.lmstudio_message: str = ""
        self.lmstudio_message_i18n: dict = {}
        self.whisper: bool = False
        self.whisper_message: str = ""
        self.whisper_message_i18n: dict = {}
        self.chromadb: bool = False
        self.chromadb_message: str = ""
        self.chromadb_message_i18n: dict = {}
        self.embeddings: bool = False
        self.embeddings_message: str = ""
        self.embeddings_message_i18n: dict = {}
        self.stable_diffusion: bool = False
        self.sd_message: str = ""
        self.sd_message_i18n: dict = {}

    @property
    def llm_ok(self) -> bool:
        """True if the active LLM provider is available."""
        if Config.LLM_PROVIDER == "lmstudio":
            return self.lmstudio
        return self.ollama

    @property
    def llm_message(self) -> str:
        """Status message for the active LLM provider."""
        if Config.LLM_PROVIDER == "lmstudio":
            return self.lmstudio_message
        return self.ollama_message

    def summary(self, lang: str = "de") -> list[dict]:
        """Return a list of dicts suitable for display.
        
        Args:
            lang: Language code for service names (default: German)
        """
        active_marker = " [ACTIVE]" if Config.LLM_PROVIDER == "ollama" else ""
        lms_active_marker = " [ACTIVE]" if Config.LLM_PROVIDER == "lmstudio" else ""
        
        ollama_name = _t("service.ollama.name", lang) + active_marker
        lmstudio_name = _t("service.lmstudio.name", lang) + lms_active_marker
        
        return [
            {
                "name": ollama_name,
                "available": self.ollama,
                "message": self.ollama_message_i18n.get(lang, self.ollama_message),
            },
            {
                "name": lmstudio_name,
                "available": self.lmstudio,
                "message": self.lmstudio_message_i18n.get(lang, self.lmstudio_message),
            },
            {
                "name": _t("service.whisper.name", lang),
                "available": self.whisper,
                "message": self.whisper_message_i18n.get(lang, self.whisper_message),
            },
            {
                "name": _t("service.chromadb.name", lang),
                "available": self.chromadb,
                "message": self.chromadb_message_i18n.get(lang, self.chromadb_message),
            },
            {
                "name": _t("service.embeddings.name", lang),
                "available": self.embeddings,
                "message": self.embeddings_message_i18n.get(lang, self.embeddings_message),
            },
            {
                "name": _t("service.stable_diffusion.name", lang),
                "available": self.stable_diffusion,
                "message": self.sd_message_i18n.get(lang, self.sd_message),
            },
        ]


# Module-level singleton — populated by init_services()
status = ServiceStatus()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_ollama(lang: str = "de") -> tuple[bool, str]:
    """Ping the Ollama API.  Returns (ok, message)."""
    url = f"{Config.OLLAMA_BASE_URL}/api/tags"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if not models:
            return True, _t("service.ollama.no_models", lang, model=Config.OLLAMA_MODEL)
        if not any(Config.OLLAMA_MODEL in m for m in models):
            return True, _t("service.ollama.model_not_found_with_run", lang, 
                          model=Config.OLLAMA_MODEL, 
                          available=", ".join(models[:5]))
        return True, _t("service.ollama.connected_model_available", lang, model=Config.OLLAMA_MODEL)
    except requests.ConnectionError:
        return False, _t("service.ollama.cannot_connect_url", lang, url=Config.OLLAMA_BASE_URL)
    except requests.Timeout:
        return False, _t("service.ollama.timeout_url", lang, url=Config.OLLAMA_BASE_URL)
    except Exception as e:
        return False, _t("service.ollama.check_failed", lang, error=str(e))


def check_lmstudio(lang: str = "de") -> tuple[bool, str]:
    """Check LM Studio API via OpenAI-compatible endpoint. Returns (ok, message)."""
    url = f"{Config.LMSTUDIO_BASE_URL}/models"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("id", "") for m in data.get("data", [])]
        if not models:
            return False, _t("service.lmstudio.no_models_loaded_url", lang, url=Config.LMSTUDIO_BASE_URL)
        # Show available models
        model_list = ", ".join(models[:3])
        return True, _t("service.lmstudio.models_available_set", lang, models=model_list)
    except requests.ConnectionError:
        return False, _t("service.lmstudio.cannot_connect_url", lang, url=Config.LMSTUDIO_BASE_URL)
    except requests.Timeout:
        return False, _t("service.lmstudio.timeout_url", lang, url=Config.LMSTUDIO_BASE_URL)
    except Exception as e:
        return False, _t("service.lmstudio.check_failed", lang, error=str(e))


def check_whisper(lang: str = "de") -> tuple[bool, str]:
    """Verify that the whisper package is importable."""
    try:
        import whisper  # noqa: F401
        return True, _t("service.whisper.installed", lang, model=Config.WHISPER_MODEL)
    except ImportError:
        return False, _t("service.whisper.not_installed", lang)


def load_whisper_model():
    """Actually load the Whisper model into memory.  Heavy — call only when
    the user first requests transcription, not at startup."""
    import whisper
    return whisper.load_model(Config.WHISPER_MODEL)


def check_chromadb(lang: str = "de") -> tuple[bool, str]:
    """Verify ChromaDB can initialise a persistent client."""
    try:
        import chromadb  # noqa: F401
        os.makedirs(Config.CHROMA_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
        client.get_or_create_collection(
            name=Config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return True, _t("service.chromadb.connected_collection", lang, 
                       collection=Config.CHROMA_COLLECTION, 
                       path=Config.CHROMA_PATH)
    except ImportError:
        return False, _t("service.chromadb.not_installed_pip", lang)
    except Exception as e:
        return False, _t("service.chromadb.init_failed", lang, error=str(e))


def check_embeddings(lang: str = "de") -> tuple[bool, str]:
    """Verify sentence-transformers is available (model loaded on demand)."""
    try:
        import sentence_transformers  # noqa: F401
        return True, _t("service.embeddings.installed_model_first_use", lang, model=Config.EMBEDDING_MODEL)
    except ImportError:
        return False, _t("service.embeddings.not_installed_pip", lang)


def init_sentence_transformer():
    """Load the sentence-transformers embedding model.  Returns the model
    object or None on failure."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(Config.EMBEDDING_MODEL)
    except Exception as e:
        log.warning("Failed to load sentence-transformer model: %s", e)
        return None


def check_stable_diffusion(lang: str = "de") -> tuple[bool, str]:
    """Ping the Stable Diffusion WebUI API if enabled."""
    if not Config.SD_ENABLED:
        return False, _t("service.sd.disabled_detail", lang)
    url = f"{Config.SD_API_URL}/sdapi/v1/sd-models"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        models = resp.json()
        count = len(models) if isinstance(models, list) else 0
        return True, _t("service.sd.connected_models_count_url", lang, count=count, url=Config.SD_API_URL)
    except requests.ConnectionError:
        return False, _t("service.sd.cannot_connect_url", lang, url=Config.SD_API_URL)
    except requests.Timeout:
        return False, _t("service.sd.timeout_url", lang, url=Config.SD_API_URL)
    except Exception as e:
        return False, _t("service.sd.check_failed", lang, error=str(e))
    """Check if FLUX model is available via Ollama."""
    if not Config.FLUX_ENABLED:
        return False, "Disabled in configuration (FLUX_ENABLED=false)"
# ---------------------------------------------------------------------------
# Aggregate initialisation
# ---------------------------------------------------------------------------


def init_services() -> ServiceStatus:
    """Run all service checks and populate the global status object.
    Called once at app startup.  Individual features check ``status.*``
    before attempting to use a service."""
    global status

    # Validate config values first
    warnings = Config.validate()
    for field, msg in warnings:
        log.warning("Config warning [%s]: %s", field, msg)

    # Check services and store messages for both languages
    status.ollama, msg_en = check_ollama("en")
    _, msg_de = check_ollama("de")
    status.ollama_message = msg_en
    status.ollama_message_i18n = {"en": msg_en, "de": msg_de}
    
    status.lmstudio, msg_en = check_lmstudio("en")
    _, msg_de = check_lmstudio("de")
    status.lmstudio_message = msg_en
    status.lmstudio_message_i18n = {"en": msg_en, "de": msg_de}
    
    status.whisper, msg_en = check_whisper("en")
    _, msg_de = check_whisper("de")
    status.whisper_message = msg_en
    status.whisper_message_i18n = {"en": msg_en, "de": msg_de}
    
    status.chromadb, msg_en = check_chromadb("en")
    _, msg_de = check_chromadb("de")
    status.chromadb_message = msg_en
    status.chromadb_message_i18n = {"en": msg_en, "de": msg_de}
    
    status.embeddings, msg_en = check_embeddings("en")
    _, msg_de = check_embeddings("de")
    status.embeddings_message = msg_en
    status.embeddings_message_i18n = {"en": msg_en, "de": msg_de}
    
    status.stable_diffusion, msg_en = check_stable_diffusion("en")
    _, msg_de = check_stable_diffusion("de")
    status.sd_message = msg_en
    status.sd_message_i18n = {"en": msg_en, "de": msg_de}

    # Auto-detect provider if not explicitly set
    if Config.LLM_PROVIDER == "auto":
        if status.lmstudio:
            Config.LLM_PROVIDER = "lmstudio"
            log.info("Auto-detected LLM provider: LM Studio")
        else:
            Config.LLM_PROVIDER = "ollama"
            log.info("Auto-detected LLM provider: Ollama")

    # Log a startup summary
    log.info("--- Service status ---")
    log.info("  Active LLM Provider: %s", Config.LLM_PROVIDER.upper())
    for svc in status.summary():
        level = "OK" if svc["available"] else "UNAVAILABLE"
        log.info("  %-45s [%s] %s", svc["name"], level, svc["message"])
    log.info("----------------------")

    return status


def refresh_service_status() -> ServiceStatus:
    """Re-run all checks (e.g. when user clicks 'refresh' on settings page)."""
    return init_services()


# ---------------------------------------------------------------------------
# Detailed diagnostics for System Status page
# ---------------------------------------------------------------------------


def get_detailed_status(lang: str = "de") -> dict:
    """Get comprehensive diagnostic information for all services.

    Args:
        lang: Language code for localized messages (default: German)
    
    Returns a dict with detailed status for each service including:
    - Connection status
    - Version/model info
    - Configuration details
    - Performance metrics
    - Setup instructions
    """
    import platform

    system_info: dict[str, Any] = {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
    }

    if HAS_PSUTIL and psutil is not None:
        system_info["memory_total_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
        system_info["memory_available_gb"] = round(psutil.virtual_memory().available / (1024**3), 1)
        system_info["memory_percent_used"] = psutil.virtual_memory().percent
        system_info["cpu_count"] = psutil.cpu_count()

    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "system": system_info,
        "services": {},
    }

    # Ollama diagnostics
    ollama_diag = _diagnose_ollama(lang)
    diagnostics["services"]["ollama"] = ollama_diag

    # LM Studio diagnostics
    lmstudio_diag = _diagnose_lmstudio(lang)
    diagnostics["services"]["lmstudio"] = lmstudio_diag

    # Whisper diagnostics
    whisper_diag = _diagnose_whisper(lang)
    diagnostics["services"]["whisper"] = whisper_diag

    # ChromaDB diagnostics
    chromadb_diag = _diagnose_chromadb(lang)
    diagnostics["services"]["chromadb"] = chromadb_diag

    # Embeddings diagnostics
    embeddings_diag = _diagnose_embeddings(lang)
    diagnostics["services"]["embeddings"] = embeddings_diag

    # Stable Diffusion diagnostics
    sd_diag = _diagnose_stable_diffusion(lang)
    diagnostics["services"]["stable_diffusion"] = sd_diag

    # Database diagnostics
    db_diag = _diagnose_database(lang)
    diagnostics["services"]["database"] = db_diag

    return diagnostics


def _diagnose_ollama(lang: str = "de") -> dict:
    """Get detailed Ollama diagnostics."""
    diag = {
        "name": _t("service.ollama.name", lang),
        "icon": "brain",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "endpoint": Config.OLLAMA_BASE_URL,
            "model": Config.OLLAMA_MODEL,
            "timeout": Config.OLLAMA_TIMEOUT,
        },
    }

    url = f"{Config.OLLAMA_BASE_URL}/api/tags"
    try:
        start = time.time()
        resp = requests.get(url, timeout=5)
        latency_ms = round((time.time() - start) * 1000, 1)
        resp.raise_for_status()

        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]

        diag["available"] = True
        diag["details"]["latency_ms"] = latency_ms
        diag["details"]["models_available"] = len(model_names)
        diag["details"]["model_list"] = model_names[:10]  # Limit to 10

        if not model_names:
            diag["message"] = _t("service.ollama.no_models_connected", lang)
            diag["setup_instructions"] = f"Run: ollama pull {Config.OLLAMA_MODEL}"
        elif not any(Config.OLLAMA_MODEL in m for m in model_names):
            diag["message"] = _t("service.ollama.model_not_found_short", lang, model=Config.OLLAMA_MODEL)
            diag["setup_instructions"] = f"Run: ollama pull {Config.OLLAMA_MODEL}"
            diag["details"]["configured_model_available"] = False
        else:
            diag["message"] = _t("service.ollama.connected_models_count", lang, count=len(model_names))
            diag["details"]["configured_model_available"] = True

            # Try to get model info
            for m in models:
                if Config.OLLAMA_MODEL in m["name"]:
                    diag["details"]["active_model"] = {
                        "name": m["name"],
                        "size": m.get("size"),
                        "modified_at": m.get("modified_at"),
                    }
                    break

    except requests.ConnectionError:
        diag["message"] = _t("service.ollama.cannot_connect", lang)
        diag["setup_instructions"] = (
            f"1. {_t('setup.ollama.step1', lang)}\n"
            f"2. {_t('setup.ollama.step2', lang)}\n"
            f"3. {_t('setup.ollama.step3', lang, model=Config.OLLAMA_MODEL)}"
        )
    except requests.Timeout:
        diag["message"] = _t("service.ollama.connection_timeout", lang)
        diag["setup_instructions"] = _t('setup.ollama.overloaded', lang)
    except Exception as e:
        diag["message"] = f"Error: {str(e)}"

    return diag


def _diagnose_lmstudio(lang: str = "de") -> dict:
    """Get detailed LM Studio diagnostics."""
    diag = {
        "name": _t("service.lmstudio.name", lang),
        "icon": "cpu",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "endpoint": Config.LMSTUDIO_BASE_URL,
            "model": Config.LMSTUDIO_MODEL,
            "provider_active": Config.LLM_PROVIDER == "lmstudio",
        },
    }

    url = f"{Config.LMSTUDIO_BASE_URL}/models"
    try:
        start = time.time()
        resp = requests.get(url, timeout=5)
        latency_ms = round((time.time() - start) * 1000, 1)
        resp.raise_for_status()

        payload = resp.json()
        models = payload.get("data", []) if isinstance(payload, dict) else []
        model_ids = [m.get("id", "") for m in models if isinstance(m, dict)]

        diag["details"]["latency_ms"] = latency_ms
        diag["details"]["models_available"] = len(model_ids)
        diag["details"]["model_list"] = model_ids[:10]

        if not model_ids:
            diag["message"] = _t("service.lmstudio.no_models_loaded", lang)
            diag["setup_instructions"] = _t("setup.lmstudio.load_model_first", lang)
            return diag

        configured_ok = any(Config.LMSTUDIO_MODEL == model_id for model_id in model_ids)
        diag["details"]["configured_model_available"] = configured_ok

        diag["available"] = True
        if configured_ok:
            diag["message"] = _t("service.lmstudio.connected_model_available", lang, model=Config.LMSTUDIO_MODEL)
        else:
            diag["message"] = _t("service.lmstudio.model_not_found", lang, model=Config.LMSTUDIO_MODEL)
            diag["setup_instructions"] = _t("setup.lmstudio.set_model", lang)

    except requests.ConnectionError:
        diag["message"] = _t("service.lmstudio.cannot_connect", lang)
        diag["setup_instructions"] = (
            f"1. {_t('setup.lmstudio.step1', lang)}\n"
            f"2. {_t('setup.lmstudio.step2', lang)}\n"
            f"3. {_t('setup.lmstudio.step4', lang)}"
        )
    except requests.Timeout:
        diag["message"] = _t("service.ollama.connection_timeout", lang)
        diag["setup_instructions"] = _t('setup.ollama.overloaded', lang)
    except Exception as e:
        diag["message"] = f"Error: {str(e)}"
        diag["setup_instructions"] = (
            f"1. {_t('setup.lmstudio.step1', lang)}\n"
            f"2. {_t('setup.lmstudio.step3', lang)}\n"
            f"3. {_t('setup.lmstudio.step2', lang)}\n"
            f"4. {_t('setup.lmstudio.step4', lang)}"
        )

    return diag


def _diagnose_whisper(lang: str = "de") -> dict:
    """Get detailed Whisper diagnostics."""
    diag = {
        "name": _t("service.whisper.name", lang),
        "icon": "microphone",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "model_size": Config.WHISPER_MODEL,
        },
    }

    try:
        import whisper
        diag["available"] = True
        diag["message"] = _t("service.whisper.installed_model_ready", lang, model=Config.WHISPER_MODEL)
        diag["details"]["whisper_version"] = getattr(whisper, "__version__", "unknown")
        diag["details"]["model_loaded"] = _whisper_model is not None

        # Model size estimates
        model_sizes = {
            "tiny": "39 MB",
            "base": "74 MB",
            "small": "244 MB",
            "medium": "769 MB",
            "large": "1550 MB",
        }
        diag["details"]["estimated_model_size"] = model_sizes.get(Config.WHISPER_MODEL, "unknown")

        # Check if ffmpeg is available
        import shutil
        diag["details"]["ffmpeg_available"] = shutil.which("ffmpeg") is not None
        if not diag["details"]["ffmpeg_available"]:
            diag["message"] += " " + _t("service.whisper.ffmpeg_warning", lang)

    except ImportError:
        diag["message"] = _t("service.whisper.not_installed_short", lang)
        diag["setup_instructions"] = (
            "1. Install Whisper: pip install openai-whisper\n"
            "2. Install ffmpeg:\n"
            "   - Windows: winget install ffmpeg\n"
            "   - Mac: brew install ffmpeg\n"
            "   - Linux: apt install ffmpeg"
        )

    return diag


def _diagnose_chromadb(lang: str = "de") -> dict:
    """Get detailed ChromaDB diagnostics."""
    diag = {
        "name": _t("service.chromadb.name", lang),
        "icon": "database",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "path": Config.CHROMA_PATH,
            "collection": Config.CHROMA_COLLECTION,
        },
    }

    try:
        import chromadb
        diag["details"]["chromadb_version"] = getattr(chromadb, "__version__", "unknown")

        os.makedirs(Config.CHROMA_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
        collection = client.get_or_create_collection(
            name=Config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        diag["available"] = True
        count = collection.count()
        diag["details"]["document_count"] = count
        diag["details"]["collection_name"] = Config.CHROMA_COLLECTION

        # Get disk usage
        total_size = 0
        if os.path.exists(Config.CHROMA_PATH):
            for dirpath, dirnames, filenames in os.walk(Config.CHROMA_PATH):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
        diag["details"]["disk_usage_mb"] = round(total_size / (1024 * 1024), 2)

        key = "service.chromadb.operational_one" if count == 1 else "service.chromadb.operational_other"
        diag["message"] = _t(key, lang, count=count)

    except ImportError:
        diag["message"] = _t("service.chromadb.not_installed", lang)
        diag["setup_instructions"] = "pip install chromadb"
    except Exception as e:
        diag["message"] = f"Error: {str(e)}"
        diag["setup_instructions"] = (
            "Try deleting the ChromaDB folder and restarting:\n"
            f"rm -rf {Config.CHROMA_PATH}"
        )

    return diag


def _diagnose_embeddings(lang: str = "de") -> dict:
    """Get detailed embeddings diagnostics."""
    diag = {
        "name": _t("service.embeddings.name", lang),
        "icon": "vector",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "model": Config.EMBEDDING_MODEL,
        },
    }

    try:
        import sentence_transformers
        diag["available"] = True
        diag["details"]["version"] = getattr(sentence_transformers, "__version__", "unknown")
        diag["message"] = _t("service.embeddings.installed_model", lang, model=Config.EMBEDDING_MODEL)

        # Check if model is downloaded
        from pathlib import Path
        cache_dir = Path.home() / ".cache" / "torch" / "sentence_transformers"
        model_name = Config.EMBEDDING_MODEL.replace("/", "_")
        model_path = cache_dir / model_name
        diag["details"]["model_cached"] = model_path.exists() if cache_dir.exists() else "unknown"

    except ImportError:
        diag["message"] = _t("service.embeddings.not_installed", lang)
        diag["setup_instructions"] = "pip install sentence-transformers"

    return diag


def _diagnose_stable_diffusion(lang: str = "de") -> dict:
    """Get detailed Stable Diffusion diagnostics."""
    diag = {
        "name": _t("service.stable_diffusion.name", lang),
        "icon": "image",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "enabled": Config.SD_ENABLED,
            "endpoint": Config.SD_API_URL,
            "default_style": Config.SD_DEFAULT_STYLE,
        },
    }

    if not Config.SD_ENABLED:
        diag["message"] = _t("service.sd.disabled", lang)
        diag["details"]["reason"] = "SD_ENABLED=false"
        diag["setup_instructions"] = (
            f"{_t('setup.sd.enable_header')}\n"
            f"1. {_t('setup.sd.install')}\n"
            f"2. {_t('setup.sd.start_api')}\n"
            f"3. {_t('setup.sd.enable_env')}"
        )
        return diag

    url = f"{Config.SD_API_URL}/sdapi/v1/sd-models"
    try:
        start = time.time()
        resp = requests.get(url, timeout=5)
        latency_ms = round((time.time() - start) * 1000, 1)
        resp.raise_for_status()

        models = resp.json()
        diag["available"] = True
        diag["details"]["latency_ms"] = latency_ms
        diag["details"]["models_count"] = len(models) if isinstance(models, list) else 0

        if isinstance(models, list) and models:
            diag["details"]["models"] = [m.get("model_name", m.get("title", "unknown"))[:50] for m in models[:5]]

        diag["message"] = _t("service.sd.connected_models_count", lang, count=len(models))

        # Try to get current model
        try:
            options_resp = requests.get(f"{Config.SD_API_URL}/sdapi/v1/options", timeout=3)
            if options_resp.ok:
                options = options_resp.json()
                diag["details"]["current_model"] = options.get("sd_model_checkpoint", "unknown")
        except:
            pass

    except requests.ConnectionError:
        diag["message"] = _t("service.sd.cannot_connect", lang)
        diag["setup_instructions"] = (
            "1. Install AUTOMATIC1111 WebUI\n"
            "2. Start with: ./webui.sh --api\n"
            f"3. Ensure it's running at {Config.SD_API_URL}"
        )
    except requests.Timeout:
        diag["message"] = _t("service.sd.connection_timeout", lang)
    except Exception as e:
        diag["message"] = f"Error: {str(e)}"

    return diag
    """Get detailed FLUX diagnostics."""
    diag = {
        "name": "FLUX (AI Images)",
        "icon": "sparkles",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "enabled": Config.FLUX_ENABLED,
            "model": Config.FLUX_MODEL,
            "steps": Config.FLUX_STEPS,
            "width": Config.FLUX_WIDTH,
            "height": Config.FLUX_HEIGHT,
        },
    }

    if not Config.FLUX_ENABLED:
        diag["message"] = "Disabled in configuration"
        diag["details"]["reason"] = "FLUX_ENABLED=false"
        diag["setup_instructions"] = (
            "To enable FLUX image generation:\n"
            "1. Ensure Ollama is running\n"
            "2. Pull FLUX model: ollama pull flux-schnell\n"
            "3. Set FLUX_ENABLED=true in .env"
        )
        return diag

    url = f"{Config.OLLAMA_BASE_URL}/api/tags"
    try:
        start = time.time()
        resp = requests.get(url, timeout=5)
        latency_ms = round((time.time() - start) * 1000, 1)
        resp.raise_for_status()

        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]
        flux_models = [m for m in model_names if "flux" in m.lower()]

        diag["details"]["latency_ms"] = latency_ms
        diag["details"]["all_models"] = model_names[:10]
        diag["details"]["flux_models"] = flux_models

        if not flux_models:
            diag["message"] = "Ollama connected, but no FLUX models found"
            diag["setup_instructions"] = (
                f"Run: ollama pull {Config.FLUX_MODEL}\n"
                "Available models: https://ollama.com/library/flux"
            )
        elif not any(Config.FLUX_MODEL in m for m in model_names):
            diag["available"] = True
            diag["message"] = f"FLUX available via '{flux_models[0]}'"
            diag["details"]["using_model"] = flux_models[0]
            diag["setup_instructions"] = (
                f"To use {Config.FLUX_MODEL}: ollama pull {Config.FLUX_MODEL}"
            )
        else:
            diag["available"] = True
            diag["message"] = f"Connected - FLUX model '{Config.FLUX_MODEL}' ready"
            diag["details"]["using_model"] = Config.FLUX_MODEL

    except requests.ConnectionError:
        diag["message"] = "Cannot connect to Ollama"
        diag["setup_instructions"] = (
            "1. Install Ollama: https://ollama.ai\n"
            "2. Start the Ollama server: ollama serve\n"
            "3. Pull FLUX: ollama pull flux-schnell"
        )
    except requests.Timeout:
        diag["message"] = "Connection timed out"
    except Exception as e:
        diag["message"] = f"Error: {str(e)}"

    return diag


def _diagnose_database(lang: str = "de") -> dict:
    """Get detailed database diagnostics."""
    import sqlite3

    diag = {
        "name": _t("service.database.name", lang),
        "icon": "storage",
        "available": False,
        "message": "",
        "details": {},
        "setup_instructions": None,
        "config": {
            "path": Config.DATABASE_PATH,
        },
    }

    try:
        if os.path.exists(Config.DATABASE_PATH):
            diag["details"]["file_size_mb"] = round(
                os.path.getsize(Config.DATABASE_PATH) / (1024 * 1024), 2
            )

            conn = sqlite3.connect(Config.DATABASE_PATH)
            cursor = conn.cursor()

            # Get SQLite version
            cursor.execute("SELECT sqlite_version()")
            diag["details"]["sqlite_version"] = cursor.fetchone()[0]

            # Count entries
            cursor.execute("SELECT COUNT(*) FROM entries")
            diag["details"]["entry_count"] = cursor.fetchone()[0]

            # Count by type
            cursor.execute("SELECT entry_type, COUNT(*) FROM entries GROUP BY entry_type")
            diag["details"]["entries_by_type"] = dict(cursor.fetchall())

            # Get table info
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            diag["details"]["tables"] = [row[0] for row in cursor.fetchall()]

            conn.close()

            diag["available"] = True
            diag["message"] = _t("service.database.operational", lang, count=diag['details']['entry_count'])
        else:
            diag["message"] = _t("service.database.not_found", lang)
            diag["available"] = True

    except Exception as e:
        diag["message"] = f"Error: {str(e)}"
        diag["setup_instructions"] = (
            "Database may be corrupted. To restore:\n"
            f"1. Backup: cp {Config.DATABASE_PATH} {Config.DATABASE_PATH}.bak\n"
            f"2. Delete: rm {Config.DATABASE_PATH}\n"
            "3. Restart the app to create a fresh database"
        )

    return diag


# Module-level cache for whisper model (loaded lazily by voice.py)
_whisper_model = None
