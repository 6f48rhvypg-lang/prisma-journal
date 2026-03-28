import os
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---------------------------------------------------------------------------
# Color theme palettes  (name -> tailwind color config)
# Used in base.html to set the primary palette dynamically.
# ---------------------------------------------------------------------------

COLOR_THEMES = {
    "ocean": {
        "50": "#f0f9ff", "100": "#e0f2fe", "200": "#bae6fd",
        "300": "#7dd3fc", "400": "#38bdf8", "500": "#0ea5e9",
        "600": "#0284c7", "700": "#0369a1", "800": "#075985",
        "900": "#0c4a6e",
    },
    "forest": {
        "50": "#f0fdf4", "100": "#dcfce7", "200": "#bbf7d0",
        "300": "#86efac", "400": "#4ade80", "500": "#22c55e",
        "600": "#16a34a", "700": "#15803d", "800": "#166534",
        "900": "#14532d",
    },
    "sunset": {
        "50": "#fff7ed", "100": "#ffedd5", "200": "#fed7aa",
        "300": "#fdba74", "400": "#fb923c", "500": "#f97316",
        "600": "#ea580c", "700": "#c2410c", "800": "#9a3412",
        "900": "#7c2d12",
    },
    "lavender": {
        "50": "#faf5ff", "100": "#f3e8ff", "200": "#e9d5ff",
        "300": "#d8b4fe", "400": "#c084fc", "500": "#a855f7",
        "600": "#9333ea", "700": "#7e22ce", "800": "#6b21a8",
        "900": "#581c87",
    },
    "slate": {
        "50": "#f8fafc", "100": "#f1f5f9", "200": "#e2e8f0",
        "300": "#cbd5e1", "400": "#94a3b8", "500": "#64748b",
        "600": "#475569", "700": "#334155", "800": "#1e293b",
        "900": "#0f172a",
    },
    "sand": {
        "50": "#fffbf2", "100": "#fef3c7", "200": "#fde68a",
        "300": "#fcd34d", "400": "#fbbf24", "500": "#f59e0b",
        "600": "#d97706", "700": "#b45309", "800": "#92400e",
        "900": "#78350f",
    },
    "berry": {
        "50": "#fff1f2", "100": "#ffe4e6", "200": "#fecdd3",
        "300": "#fda4af", "400": "#fb7185", "500": "#f43f5e",
        "600": "#e11d48", "700": "#be123c", "800": "#9f1239",
        "900": "#881337",
    },
    "monochrome": {
        "50": "#fafafa", "100": "#f4f4f5", "200": "#e4e4e7",
        "300": "#d4d4d8", "400": "#a1a1aa", "500": "#71717a",
        "600": "#52525b", "700": "#3f3f46", "800": "#27272a",
        "900": "#18181b",
    },
}

ARTWORK_STYLES = [
    "minimalist abstract",
    "watercolor",
    "geometric",
    "surreal",
    "nature inspired",
    "urban architectural",
    "cosmic space",
    "impressionist",
    "line art",
    "collage",
]

WHISPER_MODELS = ("tiny", "base", "small", "medium", "large")


class Config:
    """Central configuration. Every value can be overridden via environment
    variables or a .env file in the project root."""

    # -- Paths ---------------------------------------------------------------
    BASE_DIR = BASE_DIR
    MODEL_PATH = os.environ.get(
        "MODEL_PATH", os.path.join(BASE_DIR, "app", "models")
    )
    DATABASE_PATH = os.environ.get(
        "DB_PATH", os.path.join(BASE_DIR, "app", "database", "journal.db")
    )
    CHROMA_PATH = os.environ.get(
        "CHROMA_PATH", os.path.join(BASE_DIR, "app", "database", "chroma")
    )
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")

    # -- Flask ---------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.environ.get("DEBUG_MODE", "true").lower() == "true"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload cap

    # -- Entry limits --------------------------------------------------------
    MAX_ENTRY_LENGTH = int(os.environ.get("MAX_ENTRY_LENGTH", "50000"))

    # -- LLM Provider Selection ---------------------------------------------
    # Choose between "ollama", "lmstudio", or "auto" (detect at startup)
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto").lower()

    # -- Ollama (LLM) -------------------------------------------------------
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
    OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

    # -- LM Studio (Alternative LLM via OpenAI API) -------------------------
    LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL", "llama-3.2-3b-instruct")
    LMSTUDIO_TIMEOUT = int(os.environ.get("LMSTUDIO_TIMEOUT", "120"))

    # -- Whisper (Speech-to-text) --------------------------------------------
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

    # -- Image Generation (ComfyUI / Stable Diffusion) -----------------------
    # ComfyUI is the preferred method for high-quality artwork generation
    COMFY_ENABLED = os.environ.get("COMFY_ENABLED", "true").lower() == "true"
    COMFY_API_URL = os.environ.get("COMFY_API_URL", "http://127.0.0.1:8188")
    COMFY_WORKFLOW_MODE = os.environ.get("COMFY_WORKFLOW_MODE", "refiner")  # "base" or "refiner"
    COMFY_BASE_MODEL = os.environ.get("COMFY_BASE_MODEL", "sd_xl_base_1.0.safetensors")
    COMFY_REFINER_MODEL = os.environ.get("COMFY_REFINER_MODEL", "sd_xl_refiner_1.0.safetensors")
    
    # Legacy Stable Diffusion WebUI support (fallback)
    SD_API_URL = os.environ.get("SD_ENDPOINT", "http://localhost:7860")
    SD_ENABLED = os.environ.get("SD_ENABLED", "false").lower() == "true"
    SD_DEFAULT_STYLE = os.environ.get("SD_DEFAULT_STYLE", "minimalist abstract")

    # -- Embeddings / ChromaDB -----------------------------------------------
    EMBEDDING_MODEL = os.environ.get(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "journal_entries")

    # -- UI theme ------------------------------------------------------------
    COLOR_THEME = os.environ.get("COLOR_THEME", "monochrome")

    # -- Language / i18n -----------------------------------------------------
    DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "de")  # "de" (German) or "en" (English)

    # -- Tag Auto-Suggestion -------------------------------------------------
    TAG_MODEL = os.environ.get("TAG_MODEL", "deepseek-r1:14b")
    TAG_ENABLED = os.environ.get("TAG_ENABLED", "true").lower() == "true"
    TAG_MIN_LENGTH = int(os.environ.get("TAG_MIN_LENGTH", "50"))
    TAG_MAX_SUGGESTIONS = int(os.environ.get("TAG_MAX_SUGGESTIONS", "7"))
    TAG_DEBOUNCE_MS = int(os.environ.get("TAG_DEBOUNCE_MS", "500"))

    # -- Derived helpers (not meant to be set via env) -----------------------

    @classmethod
    def get_theme_colors(cls):
        """Return the active theme palette dict, falling back to ocean."""
        return COLOR_THEMES.get(cls.COLOR_THEME, COLOR_THEMES["ocean"])

    @classmethod
    def validate(cls):
        """Return a list of (field, message) warnings for invalid values."""
        warnings = []
        if cls.WHISPER_MODEL not in WHISPER_MODELS:
            warnings.append((
                "WHISPER_MODEL",
                f"'{cls.WHISPER_MODEL}' is not a recognised Whisper model size. "
                f"Expected one of: {', '.join(WHISPER_MODELS)}. Falling back to 'base'.",
            ))
        if cls.COLOR_THEME not in COLOR_THEMES:
            warnings.append((
                "COLOR_THEME",
                f"'{cls.COLOR_THEME}' is not a recognised theme. "
                f"Expected one of: {', '.join(COLOR_THEMES)}. Falling back to 'ocean'.",
            ))
        if cls.SD_DEFAULT_STYLE not in ARTWORK_STYLES:
            warnings.append((
                "SD_DEFAULT_STYLE",
                f"'{cls.SD_DEFAULT_STYLE}' is not a known artwork style. "
                f"Expected one of: {', '.join(ARTWORK_STYLES)}.",
            ))
        
        # Validate ComfyUI settings
        if cls.COMFY_WORKFLOW_MODE not in ("base", "refiner"):
            warnings.append((
                "COMFY_WORKFLOW_MODE",
                f"'{cls.COMFY_WORKFLOW_MODE}' is not a valid workflow mode. "
                f"Expected 'base' or 'refiner'. Falling back to 'refiner'.",
            ))
        if cls.MAX_ENTRY_LENGTH < 100:
            warnings.append((
                "MAX_ENTRY_LENGTH",
                f"MAX_ENTRY_LENGTH={cls.MAX_ENTRY_LENGTH} is unusually small. "
                "Entries shorter than 100 characters won't be very useful.",
            ))
        return warnings
