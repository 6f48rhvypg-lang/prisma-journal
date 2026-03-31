import functools
import json
import logging
import os
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from utils.i18n import get_prompt, translate
from utils.cache import cached, invalidate_cache

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database Error Handling
# ---------------------------------------------------------------------------


class DatabaseError(Exception):
    """Custom exception for database operations."""

    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        self.operation = operation
        self.message = message
        self.original_error = original_error
        super().__init__(f"Database error during {operation}: {message}")


def db_operation(operation_name: Optional[str] = None):
    """Decorator for database operations with error handling and logging.

    Wraps functions to catch SQLite errors, log them, and optionally re-raise
    with a more descriptive DatabaseError.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            try:
                return func(*args, **kwargs)
            except sqlite3.IntegrityError as e:
                log.error("Database integrity error in %s: %s", op_name, e)
                raise DatabaseError(
                    op_name,
                    f"Data integrity violation: {str(e)}",
                    original_error=e,
                )
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if "locked" in error_msg:
                    log.warning("Database locked in %s: %s", op_name, e)
                    raise DatabaseError(
                        op_name,
                        "Database is busy. Please try again.",
                        original_error=e,
                    )
                elif "no such table" in error_msg:
                    log.error("Missing table in %s: %s", op_name, e)
                    raise DatabaseError(
                        op_name,
                        "Database schema error. Try restarting the application.",
                        original_error=e,
                    )
                else:
                    log.error("Database operational error in %s: %s", op_name, e)
                    raise DatabaseError(op_name, str(e), original_error=e)
            except sqlite3.DatabaseError as e:
                log.error("Database error in %s: %s", op_name, e)
                raise DatabaseError(
                    op_name,
                    "Database error occurred. The database may be corrupted.",
                    original_error=e,
                )
            except Exception as e:
                log.exception("Unexpected error in %s", op_name)
                raise

        return wrapper

    return decorator


def safe_db_operation(func):
    """Decorator that catches errors and returns None instead of raising.

    Use for non-critical operations where failure should not break the app.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.warning("Database operation %s failed (non-critical): %s", func.__name__, e)
            return None

    return wrapper

# ---------------------------------------------------------------------------
# Valid enum values
# ---------------------------------------------------------------------------

ENTRY_TYPES = ("text", "voice", "framework", "scan")
PLUTCHIK_EMOTIONS = (
    "joy", "trust", "fear", "surprise",
    "sadness", "disgust", "anger", "anticipation",
)
EMOTION_INTENSITIES = ("low", "medium", "high")

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def get_connection():
    """Get a SQLite connection with row factory enabled."""
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


@db_operation("init_db")
def init_db():
    """Create all tables, indexes, and seed data if needed."""
    log.info("Initializing database at %s", Config.DATABASE_PATH)
    conn = get_connection()
    conn.executescript(
        """
        -- Frameworks (must exist before entries due to FK)
        CREATE TABLE IF NOT EXISTS frameworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            questions TEXT NOT NULL DEFAULT '[]',  -- JSON array
            category TEXT NOT NULL DEFAULT '',
            is_builtin INTEGER NOT NULL DEFAULT 0
        );

        -- Entries
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,                         -- UUID
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL DEFAULT 0,
            writing_duration INTEGER NOT NULL DEFAULT 0, -- seconds
            entry_type TEXT NOT NULL DEFAULT 'text'
                CHECK (entry_type IN ('text', 'voice', 'framework', 'scan')),
            framework_id INTEGER REFERENCES frameworks(id) ON DELETE SET NULL,
            summary TEXT,                                -- AI-generated
            artwork_path TEXT,
            artwork_style TEXT
        );

        -- Emotions (Plutchik's wheel)
        CREATE TABLE IF NOT EXISTS emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            emotion TEXT NOT NULL
                CHECK (emotion IN (
                    'joy', 'trust', 'fear', 'surprise',
                    'sadness', 'disgust', 'anger', 'anticipation'
                )),
            intensity TEXT NOT NULL DEFAULT 'medium'
                CHECK (intensity IN ('low', 'medium', 'high')),
            frequency REAL NOT NULL DEFAULT 0.5
                CHECK (frequency >= 0.0 AND frequency <= 1.0)
        );

        -- Tags
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            tag_name TEXT NOT NULL
        );

        -- Embeddings
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            embedding_vector TEXT NOT NULL,   -- JSON array of floats
            model_version TEXT NOT NULL DEFAULT ''
        );

        -- Settings
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL               -- plain text or JSON
        );

        -- Prompts (journal writing prompts)
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            text TEXT NOT NULL
        );

        -- Daily reflection questions
        CREATE TABLE IF NOT EXISTS daily_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            question_text TEXT NOT NULL,
            is_answered INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_daily_questions_date ON daily_questions(date);

        -- Canonical tag definitions (lightweight taxonomy)
        CREATE TABLE IF NOT EXISTS tag_defs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL UNIQUE,
            tag_type TEXT NOT NULL DEFAULT 'auto'
                CHECK (tag_type IN ('auto', 'user', 'baustelle', 'system')),
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP
        );

        -- Tag aliases for normalization
        CREATE TABLE IF NOT EXISTS tag_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT NOT NULL UNIQUE,
            canonical_tag_id INTEGER NOT NULL REFERENCES tag_defs(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Baustellen (curated ongoing concerns)
        CREATE TABLE IF NOT EXISTS baustellen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headline TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            core_problem TEXT,
            recent_development TEXT,
            status TEXT NOT NULL DEFAULT 'stable'
                CHECK (status IN ('escalating', 'stable', 'improving', 'dormant', 'closed')),
            urgency INTEGER NOT NULL DEFAULT 3
                CHECK (urgency >= 1 AND urgency <= 5),
            is_pinned INTEGER NOT NULL DEFAULT 0,
            is_auto_generated INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_mentioned_at TIMESTAMP,
            entry_count INTEGER NOT NULL DEFAULT 0
        );

        -- Link tags to Baustellen (many-to-many with weight)
        CREATE TABLE IF NOT EXISTS baustelle_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baustelle_id INTEGER NOT NULL REFERENCES baustellen(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tag_defs(id) ON DELETE CASCADE,
            weight REAL NOT NULL DEFAULT 1.0,
            is_primary INTEGER NOT NULL DEFAULT 0,
            UNIQUE(baustelle_id, tag_id)
        );

        -- Link entries to Baustellen
        CREATE TABLE IF NOT EXISTS entry_baustellen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            baustelle_id INTEGER NOT NULL REFERENCES baustellen(id) ON DELETE CASCADE,
            confidence REAL NOT NULL DEFAULT 0.5,
            link_source TEXT NOT NULL DEFAULT 'auto'
                CHECK (link_source IN ('auto', 'manual', 'user', 'tag_match')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entry_id, baustelle_id)
        );

        -- Indexes for smart tag system
        CREATE INDEX IF NOT EXISTS idx_tag_defs_name ON tag_defs(tag_name);
        CREATE INDEX IF NOT EXISTS idx_tag_defs_type ON tag_defs(tag_type);
        CREATE INDEX IF NOT EXISTS idx_tag_defs_active ON tag_defs(is_active);
        CREATE INDEX IF NOT EXISTS idx_tag_aliases_alias ON tag_aliases(alias);
        CREATE INDEX IF NOT EXISTS idx_tag_aliases_canonical ON tag_aliases(canonical_tag_id);
        CREATE INDEX IF NOT EXISTS idx_baustellen_status ON baustellen(status);
        CREATE INDEX IF NOT EXISTS idx_baustellen_pinned ON baustellen(is_pinned);
        CREATE INDEX IF NOT EXISTS idx_baustellen_urgency ON baustellen(urgency DESC);
        CREATE INDEX IF NOT EXISTS idx_baustellen_last_mentioned ON baustellen(last_mentioned_at DESC);
        CREATE INDEX IF NOT EXISTS idx_baustelle_tags_baustelle ON baustelle_tags(baustelle_id);
        CREATE INDEX IF NOT EXISTS idx_baustelle_tags_tag ON baustelle_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_entry_baustellen_entry ON entry_baustellen(entry_id);
        CREATE INDEX IF NOT EXISTS idx_entry_baustellen_baustelle ON entry_baustellen(baustelle_id);

        -- Dismissed Baustellen suggestions (user explicitly ignored these patterns)
        CREATE TABLE IF NOT EXISTS dismissed_baustellen_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_slug TEXT NOT NULL UNIQUE,
            dismissed_count INTEGER NOT NULL DEFAULT 1,
            dismissed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes for frequently queried fields
        CREATE INDEX IF NOT EXISTS idx_entries_created_at
            ON entries(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_entries_entry_type
            ON entries(entry_type);
        CREATE INDEX IF NOT EXISTS idx_entries_framework_id
            ON entries(framework_id);

        CREATE INDEX IF NOT EXISTS idx_emotions_entry_id
            ON emotions(entry_id);
        CREATE INDEX IF NOT EXISTS idx_emotions_emotion
            ON emotions(emotion);
        CREATE INDEX IF NOT EXISTS idx_emotions_intensity
            ON emotions(intensity);

        CREATE INDEX IF NOT EXISTS idx_tags_entry_id
            ON tags(entry_id);
        CREATE INDEX IF NOT EXISTS idx_tags_tag_name
            ON tags(tag_name);

        CREATE INDEX IF NOT EXISTS idx_embeddings_entry_id
            ON embeddings(entry_id);

        -- Composite indexes for optimized queries
        CREATE INDEX IF NOT EXISTS idx_emotions_entry_frequency
            ON emotions(entry_id, frequency DESC);
        CREATE INDEX IF NOT EXISTS idx_tags_name_entry
            ON tags(tag_name, entry_id);
        CREATE INDEX IF NOT EXISTS idx_entries_type_created
            ON entries(entry_type, created_at DESC);
    """
    )
    conn.commit()

    # Run schema migrations for existing databases
    _migrate_schema(conn)

    # Seed default data if tables are empty
    if conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0] == 0:
        _seed_prompts(conn)
    if conn.execute("SELECT COUNT(*) FROM frameworks").fetchone()[0] == 0:
        _seed_frameworks(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


def _migrate_schema(conn):
    """Apply schema migrations for existing databases."""
    # Check if title_image_path column exists on entries table
    cursor = conn.execute("PRAGMA table_info(entries)")
    columns = {row[1] for row in cursor.fetchall()}

    if "title_image_path" not in columns:
        try:
            conn.execute("ALTER TABLE entries ADD COLUMN title_image_path TEXT")
            conn.commit()
            log.info("Migration: Added title_image_path column to entries table")
        except Exception as e:
            log.warning("Migration for title_image_path failed (may already exist): %s", e)

    if "title" not in columns:
        try:
            conn.execute("ALTER TABLE entries ADD COLUMN title TEXT")
            conn.commit()
            log.info("Migration: Added title column to entries table")
        except Exception as e:
            log.warning("Migration for title failed (may already exist): %s", e)

    # Migration: Add is_builtin column to frameworks table
    fw_cursor = conn.execute("PRAGMA table_info(frameworks)")
    fw_columns = {row[1] for row in fw_cursor.fetchall()}
    if "is_builtin" not in fw_columns:
        try:
            conn.execute("ALTER TABLE frameworks ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 0")
            _builtin_names = (
                "Morning Pages", "Gratitude Practice", "CBT Thought Record",
                "Stoic Reflection", "Future Self", "Problem Solving",
                "Goal Setting", "Relationship Reflection", "Energy Audit",
                "Creative Brainstorm", "Fear Setting", "Weekly Review",
            )
            placeholders = ",".join("?" * len(_builtin_names))
            conn.execute(
                f"UPDATE frameworks SET is_builtin=1 WHERE name IN ({placeholders})",
                _builtin_names,
            )
            conn.commit()
            log.info("Migration: Added is_builtin column to frameworks table")
        except Exception as e:
            log.warning("Migration for is_builtin failed (may already exist): %s", e)

    # Migration: Create smart tag system tables
    _migrate_create_smart_tag_tables(conn)


def _migrate_create_smart_tag_tables(conn):
    """Create new tables for the smart tag system if they don't exist."""
    # Check if tag_defs table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tag_defs'")
    if cursor.fetchone():
        log.debug("Smart tag tables already exist, skipping migration")
        return

    try:
        conn.executescript(
            """
            -- Canonical tag definitions
            CREATE TABLE IF NOT EXISTS tag_defs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name TEXT NOT NULL UNIQUE,
                tag_type TEXT NOT NULL DEFAULT 'auto'
                    CHECK (tag_type IN ('auto', 'user', 'baustelle', 'system')),
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            );

            -- Tag aliases for normalization
            CREATE TABLE IF NOT EXISTS tag_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                canonical_tag_id INTEGER NOT NULL REFERENCES tag_defs(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- Baustellen (curated ongoing concerns)
            CREATE TABLE IF NOT EXISTS baustellen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                headline TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                core_problem TEXT,
                recent_development TEXT,
                status TEXT NOT NULL DEFAULT 'stable'
                    CHECK (status IN ('escalating', 'stable', 'improving', 'dormant', 'closed')),
                urgency INTEGER NOT NULL DEFAULT 3
                    CHECK (urgency >= 1 AND urgency <= 5),
                is_pinned INTEGER NOT NULL DEFAULT 0,
                is_auto_generated INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_mentioned_at TIMESTAMP,
                entry_count INTEGER NOT NULL DEFAULT 0
            );

            -- Link tags to Baustellen
            CREATE TABLE IF NOT EXISTS baustelle_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                baustelle_id INTEGER NOT NULL REFERENCES baustellen(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tag_defs(id) ON DELETE CASCADE,
                weight REAL NOT NULL DEFAULT 1.0,
                is_primary INTEGER NOT NULL DEFAULT 0,
                UNIQUE(baustelle_id, tag_id)
            );

            -- Link entries to Baustellen
            CREATE TABLE IF NOT EXISTS entry_baustellen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                baustelle_id INTEGER NOT NULL REFERENCES baustellen(id) ON DELETE CASCADE,
                confidence REAL NOT NULL DEFAULT 0.5,
                link_source TEXT NOT NULL DEFAULT 'auto'
                    CHECK (link_source IN ('auto', 'manual', 'user', 'tag_match')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entry_id, baustelle_id)
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_tag_defs_name ON tag_defs(tag_name);
            CREATE INDEX IF NOT EXISTS idx_tag_defs_type ON tag_defs(tag_type);
            CREATE INDEX IF NOT EXISTS idx_tag_defs_active ON tag_defs(is_active);
            CREATE INDEX IF NOT EXISTS idx_tag_aliases_alias ON tag_aliases(alias);
            CREATE INDEX IF NOT EXISTS idx_tag_aliases_canonical ON tag_aliases(canonical_tag_id);
            CREATE INDEX IF NOT EXISTS idx_baustellen_status ON baustellen(status);
            CREATE INDEX IF NOT EXISTS idx_baustellen_pinned ON baustellen(is_pinned);
            CREATE INDEX IF NOT EXISTS idx_baustellen_urgency ON baustellen(urgency DESC);
            CREATE INDEX IF NOT EXISTS idx_baustellen_last_mentioned ON baustellen(last_mentioned_at DESC);
            CREATE INDEX IF NOT EXISTS idx_baustelle_tags_baustelle ON baustelle_tags(baustelle_id);
            CREATE INDEX IF NOT EXISTS idx_baustelle_tags_tag ON baustelle_tags(tag_id);
            CREATE INDEX IF NOT EXISTS idx_entry_baustellen_entry ON entry_baustellen(entry_id);
            CREATE INDEX IF NOT EXISTS idx_entry_baustellen_baustelle ON entry_baustellen(baustelle_id);
            """
        )
        conn.commit()
        log.info("Migration: Created smart tag system tables")

        # Backfill: Create tag_defs from existing tags
        _backfill_tag_defs_from_existing(conn)

    except Exception as e:
        log.error("Migration for smart tag system failed: %s", e)


def _backfill_tag_defs_from_existing(conn):
    """Create tag definitions from existing tags."""
    try:
        # Get all unique tag names
        rows = conn.execute(
            "SELECT DISTINCT tag_name FROM tags WHERE tag_name IS NOT NULL AND tag_name != ''"
        ).fetchall()

        for row in rows:
            tag_name = row["tag_name"]
            # Insert if not exists
            conn.execute(
                """INSERT OR IGNORE INTO tag_defs (tag_name, tag_type, is_active)
                   VALUES (?, 'auto', 1)""",
                (tag_name,)
            )

        conn.commit()
        log.info("Backfilled %d tag definitions from existing tags", len(rows))
    except Exception as e:
        log.warning("Failed to backfill tag definitions: %s", e)



def _seed_prompts(conn):
    """Insert default journal prompts."""
    prompts = [
        ("gratitude", "What are three things you're grateful for today?"),
        ("gratitude", "Who made a positive impact on your life recently and how?"),
        ("reflection", "What challenged you today and what did you learn from it?"),
        ("reflection", "What would you do differently if you could relive today?"),
        ("growth", "What is one skill you'd like to develop and why?"),
        ("growth", "Describe a recent failure and the lesson it taught you."),
        ("creativity", "If you could create anything without limits, what would it be?"),
        ("creativity", "Write about a dream you had recently and what it might mean."),
        ("mindfulness", "Describe your current emotional state in detail."),
        ("mindfulness", "What sensations do you notice in your body right now?"),
    ]
    conn.executemany("INSERT INTO prompts (category, text) VALUES (?, ?)", prompts)
    conn.commit()


def _seed_frameworks(conn):
    """Insert default journaling frameworks."""
    frameworks = [
        (
            "Morning Pages",
            "Stream-of-consciousness writing to clear the mind.",
            json.dumps([
                {
                    "id": "morning_pages_mind",
                    "question": "What is on your mind right now?",
                    "placeholder": "Let everything spill out without editing...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "morning_pages_unresolved",
                    "question": "What feels unfinished or unresolved?",
                    "placeholder": "Name the loose ends that are taking up space...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "morning_pages_meaningful",
                    "question": "What would make today feel meaningful?",
                    "placeholder": "One or two outcomes that would matter...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "daily",
        ),
        (
            "Gratitude Practice",
            "Focus on what you're thankful for and why it matters.",
            json.dumps([
                {
                    "id": "gratitude_three",
                    "question": "Three things I'm grateful for today",
                    "placeholder": "List three specific things...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "gratitude_why",
                    "question": "Why am I grateful for each?",
                    "placeholder": "What makes each one meaningful?",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "gratitude_express",
                    "question": "How can I express this gratitude?",
                    "placeholder": "A message, a gesture, a habit...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "gratitude",
        ),
        (
            "CBT Thought Record",
            "Cognitive Behavioral Therapy structured thought analysis.",
            json.dumps([
                {
                    "id": "cbt_situation",
                    "question": "Situation: What happened?",
                    "placeholder": "Describe the situation objectively...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "cbt_thoughts",
                    "question": "Thoughts: What went through your mind?",
                    "placeholder": "Automatic thoughts, interpretations, assumptions...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "cbt_emotions",
                    "question": "Emotions: How did you feel?",
                    "placeholder": "Name the emotions and intensity...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "cbt_behaviors",
                    "question": "Behaviors: What did you do?",
                    "placeholder": "Actions, avoidance, or reactions...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "cbt_alternative",
                    "question": "Alternative thoughts: What else could be true?",
                    "placeholder": "A more balanced or compassionate reframe...",
                    "type": "textarea",
                    "required": True,
                },
            ]),
            "therapy",
        ),
        (
            "Stoic Reflection",
            "Evening reflection inspired by Stoic philosophy.",
            json.dumps([
                {
                    "id": "stoic_control",
                    "question": "What is within my control?",
                    "placeholder": "Actions, attitudes, choices...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "stoic_not_control",
                    "question": "What is outside my control?",
                    "placeholder": "Other people's actions, outcomes, timing...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "stoic_focus",
                    "question": "How can I focus on what I can control?",
                    "placeholder": "One small step or mindset shift...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "stoic_virtue",
                    "question": "What virtue can I practice today?",
                    "placeholder": "Wisdom, courage, justice, temperance...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "reflection",
        ),
        (
            "Future Self",
            "Write with your long-term self in mind.",
            json.dumps([
                {
                    "id": "future_five_years",
                    "question": "Where do I want to be in 5 years?",
                    "placeholder": "Paint the picture in detail...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "future_thanks",
                    "question": "What would my future self thank me for doing today?",
                    "placeholder": "One action or habit to start now...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "future_habits",
                    "question": "What habits should I build?",
                    "placeholder": "Behaviors that move me closer to that vision...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "vision",
        ),
        (
            "Problem Solving",
            "A practical structure for working through challenges.",
            json.dumps([
                {
                    "id": "problem_define",
                    "question": "What is the problem?",
                    "placeholder": "Describe the problem in one or two sentences...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "problem_solutions",
                    "question": "What are 3 possible solutions?",
                    "placeholder": "List three options without judging them...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "problem_pros_cons",
                    "question": "What are the pros and cons of each?",
                    "placeholder": "Costs, benefits, risks...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "problem_first_step",
                    "question": "Which will I try first?",
                    "placeholder": "Pick one and define the first step...",
                    "type": "textarea",
                    "required": True,
                },
            ]),
            "decision",
        ),
        (
            "Goal Setting",
            "Clarify your goals and commit to the next action.",
            json.dumps([
                {
                    "id": "goal_define",
                    "question": "What is the goal?",
                    "placeholder": "Be specific and measurable...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "goal_why",
                    "question": "Why does it matter?",
                    "placeholder": "The motivation behind this goal...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "goal_milestone",
                    "question": "What is the next milestone?",
                    "placeholder": "Define a checkpoint you can reach soon...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "goal_first_step",
                    "question": "What is the first step?",
                    "placeholder": "One small action you can take this week...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "goal_obstacles",
                    "question": "What could get in the way and how will I handle it?",
                    "placeholder": "Plan for likely obstacles...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "planning",
        ),
        (
            "Relationship Reflection",
            "Explore connection, needs, and communication.",
            json.dumps([
                {
                    "id": "relationship_person",
                    "question": "Who is on my mind?",
                    "placeholder": "A person or relationship you want to reflect on...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "relationship_contribution",
                    "question": "What did I contribute to the relationship?",
                    "placeholder": "Actions, intentions, or tone...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "relationship_need",
                    "question": "What do I need from them?",
                    "placeholder": "Support, clarity, boundaries...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "relationship_request",
                    "question": "What can I express or ask for?",
                    "placeholder": "A message or next conversation...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "relationships",
        ),
        (
            "Energy Audit",
            "Track what fuels or drains your energy.",
            json.dumps([
                {
                    "id": "energy_up",
                    "question": "What energized me today?",
                    "placeholder": "People, tasks, moments...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "energy_down",
                    "question": "What drained me today?",
                    "placeholder": "Stressors, obligations, interruptions...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "energy_pattern",
                    "question": "What pattern do I notice?",
                    "placeholder": "Themes or recurring triggers...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "energy_change",
                    "question": "One change to protect my energy",
                    "placeholder": "A boundary or adjustment to try...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "wellbeing",
        ),
        (
            "Creative Brainstorm",
            "Generate ideas without judgment.",
            json.dumps([
                {
                    "id": "creative_seed",
                    "question": "What idea do I want to explore?",
                    "placeholder": "Describe the seed of the idea...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "creative_ten",
                    "question": "Ten quick variations or extensions",
                    "placeholder": "List fast, imperfect ideas...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "creative_constraint",
                    "question": "What constraint could make it better?",
                    "placeholder": "Time, budget, audience, format...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "creative_experiment",
                    "question": "First tiny experiment to try",
                    "placeholder": "What can I test in 30 minutes?",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "creativity",
        ),
        (
            "Fear Setting",
            "Explore the cost of fear and the upside of action.",
            json.dumps([
                {
                    "id": "fear_avoid",
                    "question": "What am I avoiding?",
                    "placeholder": "Name the action or decision you are resisting...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "fear_worst",
                    "question": "What is the worst-case scenario?",
                    "placeholder": "Imagine the realistic worst case...",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "fear_repair",
                    "question": "How could I prevent or repair the damage?",
                    "placeholder": "Mitigation or recovery steps...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "fear_inaction",
                    "question": "What is the cost of inaction?",
                    "placeholder": "What happens if I do nothing for 6 months?",
                    "type": "textarea",
                    "required": True,
                },
            ]),
            "courage",
        ),
        (
            "Weekly Review",
            "Reflect on the week to close loops and reset.",
            json.dumps([
                {
                    "id": "weekly_wins",
                    "question": "What wins am I proud of?",
                    "placeholder": "Big or small, list what went well...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "weekly_challenges",
                    "question": "What challenged me?",
                    "placeholder": "Moments of friction or fatigue...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "weekly_lessons",
                    "question": "What did I learn?",
                    "placeholder": "Insights, patterns, or lessons...",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "weekly_focus",
                    "question": "What will I focus on next week?",
                    "placeholder": "One or two priorities...",
                    "type": "textarea",
                    "required": False,
                },
            ]),
            "review",
        ),
    ]
    conn.executemany(
        "INSERT INTO frameworks (name, description, questions, category, is_builtin) VALUES (?, ?, ?, ?, 1)",
        frameworks,
    )
    conn.commit()


def _normalize_questions(questions):
    """Normalize framework questions into a list of metadata objects."""
    if not isinstance(questions, list):
        return []

    normalized = []
    for idx, item in enumerate(questions, start=1):
        if isinstance(item, str):
            normalized.append({
                "id": f"q{idx}",
                "question": item,
                "placeholder": "",
                "type": "textarea",
                "required": False,
            })
            continue

        if not isinstance(item, dict):
            continue

        question_text = item.get("question") or item.get("text") or ""
        if not question_text:
            continue

        normalized.append({
            "id": item.get("id") or f"q{idx}",
            "question": question_text,
            "placeholder": item.get("placeholder", ""),
            "type": item.get("type", "textarea"),
            "required": bool(item.get("required", False)),
        })

    return normalized


# ---------------------------------------------------------------------------
# Helper: generate UUID
# ---------------------------------------------------------------------------


def _new_id():
    return str(uuid.uuid4())


def _word_count(text):
    return len(text.split()) if text and text.strip() else 0


def _attach_emotions_and_tags(conn, entries):
    """Batch-load emotions and tags for multiple entries.

    Replaces N+1 queries with 2 batch queries, reducing 101 queries to 3
    for 50 entries.
    """
    if not entries:
        return entries

    entry_ids = [e["id"] for e in entries]
    placeholders = ",".join("?" * len(entry_ids))

    # Batch query for all emotions
    emotions_rows = conn.execute(
        f"SELECT * FROM emotions WHERE entry_id IN ({placeholders}) ORDER BY frequency DESC",
        entry_ids
    ).fetchall()

    # Batch query for all tags
    tags_rows = conn.execute(
        f"SELECT entry_id, tag_name FROM tags WHERE entry_id IN ({placeholders})",
        entry_ids
    ).fetchall()

    # Group by entry_id
    emotions_map = {}
    for r in emotions_rows:
        emotions_map.setdefault(r["entry_id"], []).append(dict(r))

    tags_map = {}
    for r in tags_rows:
        tags_map.setdefault(r["entry_id"], []).append(r["tag_name"])

    # Attach to entries
    for entry in entries:
        entry["emotions"] = emotions_map.get(entry["id"], [])
        entry["tags"] = tags_map.get(entry["id"], [])

    return entries


# ---------------------------------------------------------------------------
# Entry CRUD
# ---------------------------------------------------------------------------


@db_operation("create_entry")
def create_entry(
    content,
    entry_type="text",
    framework_id=None,
    writing_duration=0,
    created_at=None,
    summary=None,
    artwork_path=None,
    artwork_style=None,
    title=None,
):
    """Create a new journal entry. Returns the UUID string."""
    # Validate entry type
    if entry_type not in ENTRY_TYPES:
        log.warning("Invalid entry_type '%s', defaulting to 'text'", entry_type)
        entry_type = "text"

    entry_id = _new_id()
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO entries
               (id, created_at, modified_at, content, word_count, writing_duration,
                entry_type, framework_id, summary, artwork_path, artwork_style, title)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                created_at or now,
                now,
                content,
                _word_count(content),
                writing_duration,
                entry_type,
                framework_id,
                summary,
                artwork_path,
                artwork_style,
                title,
            ),
        )
        conn.commit()
        invalidate_cache()  # Clear cached aggregations
        log.debug("Created entry %s (type=%s, words=%d)", entry_id, entry_type, _word_count(content))
        return entry_id
    finally:
        conn.close()


@db_operation("get_entry")
def get_entry(entry_id):
    """Fetch a single entry by UUID. Returns dict with emotions & tags attached."""
    if not entry_id:
        return None

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        entry = dict(row)
        entry["emotions"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM emotions WHERE entry_id = ? ORDER BY frequency DESC",
                (entry_id,),
            ).fetchall()
        ]
        entry["tags"] = [
            r["tag_name"]
            for r in conn.execute(
                "SELECT tag_name FROM tags WHERE entry_id = ?", (entry_id,)
            ).fetchall()
        ]
        return entry
    finally:
        conn.close()


def get_all_entries(limit=50, offset=0):
    """Fetch entries with their emotions and tags."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM entries ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()

    entries = [dict(row) for row in rows]
    _attach_emotions_and_tags(conn, entries)
    conn.close()
    return entries


@db_operation("update_entry")
def update_entry(entry_id, **kwargs):
    """Update allowed fields on an entry. Recalculates word_count if content changes."""
    if not entry_id:
        return

    allowed = {
        "content", "entry_type", "framework_id", "writing_duration",
        "summary", "artwork_path", "artwork_style", "created_at", "title",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    # Validate entry_type if provided
    if "entry_type" in fields and fields["entry_type"] not in ENTRY_TYPES:
        log.warning("Invalid entry_type '%s' in update, ignoring", fields["entry_type"])
        del fields["entry_type"]
        if not fields:
            return

    if "content" in fields:
        fields["word_count"] = _word_count(fields["content"])
    fields["modified_at"] = datetime.now().isoformat()

    conn = get_connection()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [entry_id]
        conn.execute(f"UPDATE entries SET {set_clause} WHERE id = ?", values)
        conn.commit()
        invalidate_cache()  # Clear cached aggregations
        log.debug("Updated entry %s: %s", entry_id, list(fields.keys()))
    finally:
        conn.close()


@db_operation("delete_entry")
def delete_entry(entry_id):
    """Delete an entry (cascades to emotions, tags, embeddings)."""
    if not entry_id:
        return

    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        invalidate_cache()  # Clear cached aggregations
        if cursor.rowcount > 0:
            log.info("Deleted entry %s", entry_id)
        else:
            log.warning("Attempted to delete non-existent entry %s", entry_id)
    finally:
        conn.close()


def _build_filter_clauses(date_from=None, date_to=None, emotions=None,
                           tags=None, entry_types=None, framework_ids=None):
    """Build WHERE clause fragments and params for filtered entry queries."""
    clauses = []
    params = []

    if date_from:
        clauses.append("e.created_at >= ?")
        params.append(date_from)
    if date_to:
        try:
            # Calculate next day to handle both 'T' and space separators in ISO timestamps
            # e.created_at < '2023-10-28' correctly covers '2023-10-27T23:59...'
            dt_obj = datetime.strptime(date_to, "%Y-%m-%d")
            next_day = (dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")
            clauses.append("e.created_at < ?")
            params.append(next_day)
        except (ValueError, TypeError):
            # Fallback if date format is unexpected
            clauses.append("e.created_at <= ?")
            params.append(date_to + " 23:59:59")
    if emotions:
        placeholders = ",".join("?" for _ in emotions)
        clauses.append(
            f"EXISTS (SELECT 1 FROM emotions em WHERE em.entry_id = e.id "
            f"AND em.emotion IN ({placeholders}))"
        )
        params.extend(emotions)
    if tags:
        placeholders = ",".join("?" for _ in tags)
        clauses.append(
            f"EXISTS (SELECT 1 FROM tags t WHERE t.entry_id = e.id "
            f"AND t.tag_name IN ({placeholders}))"
        )
        params.extend(tags)
    if entry_types:
        placeholders = ",".join("?" for _ in entry_types)
        clauses.append(f"e.entry_type IN ({placeholders})")
        params.extend(entry_types)
    if framework_ids:
        placeholders = ",".join("?" for _ in framework_ids)
        clauses.append(f"e.framework_id IN ({placeholders})")
        params.extend(framework_ids)

    where_sql = (" AND ".join(clauses)) if clauses else "1=1"
    return where_sql, params


def get_filtered_entries(limit=20, offset=0, sort_by="created_at", sort_dir="DESC",
                         date_from=None, date_to=None, emotions=None, tags=None,
                         entry_types=None, framework_ids=None):
    """Fetch entries with filtering, sorting, and pagination."""
    sort_columns = {
        "created_at": "e.created_at",
        "word_count": "e.word_count",
    }
    sort_dir = sort_dir.upper() if sort_dir and sort_dir.upper() in ("ASC", "DESC") else "DESC"

    where_sql, params = _build_filter_clauses(
        date_from, date_to, emotions, tags, entry_types, framework_ids
    )

    if sort_by == "emotion":
        order_clause = (
            f"(SELECT em.emotion FROM emotions em WHERE em.entry_id = e.id "
            f"ORDER BY em.frequency DESC LIMIT 1) {sort_dir}, e.created_at DESC"
        )
    elif sort_by == "framework":
        order_clause = (
            f"(SELECT f.name FROM frameworks f WHERE f.id = e.framework_id) {sort_dir}, "
            f"e.created_at DESC"
        )
    else:
        col = sort_columns.get(sort_by, "e.created_at")
        order_clause = f"{col} {sort_dir}"

    query = f"""
        SELECT e.* FROM entries e
        WHERE {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    entries = [dict(row) for row in rows]
    _attach_emotions_and_tags(conn, entries)
    conn.close()
    return entries


def get_filtered_entry_count(date_from=None, date_to=None, emotions=None,
                              tags=None, entry_types=None, framework_ids=None):
    """Count entries matching the given filters."""
    where_sql, params = _build_filter_clauses(
        date_from, date_to, emotions, tags, entry_types, framework_ids
    )
    conn = get_connection()
    count = conn.execute(
        f"SELECT COUNT(*) FROM entries e WHERE {where_sql}", params
    ).fetchone()[0]
    conn.close()
    return count


def get_unique_emotions():
    """Return sorted list of distinct emotion names used in entries."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT emotion FROM emotions ORDER BY emotion"
    ).fetchall()
    conn.close()
    return [r["emotion"] for r in rows]


def get_unique_entry_types():
    """Return sorted list of distinct entry types used."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT entry_type FROM entries ORDER BY entry_type"
    ).fetchall()
    conn.close()
    return [r["entry_type"] for r in rows]


def bulk_delete_entries(entry_ids):
    """Delete multiple entries by ID. Returns count of deleted rows."""
    if not entry_ids:
        return 0
    entry_ids = entry_ids[:100]  # cap at 100
    placeholders = ",".join("?" for _ in entry_ids)
    conn = get_connection()
    cursor = conn.execute(
        f"DELETE FROM entries WHERE id IN ({placeholders})", entry_ids
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    invalidate_cache()  # Clear cached aggregations
    return deleted


def get_entries_for_export(entry_ids):
    """Fetch full entry data for given IDs, suitable for JSON export."""
    if not entry_ids:
        return []
    entry_ids = entry_ids[:100]
    conn = get_connection()
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT * FROM entries WHERE id IN ({placeholders})", entry_ids
    ).fetchall()
    entries = [dict(row) for row in rows]
    _attach_emotions_and_tags(conn, entries)
    conn.close()
    return entries


def get_all_entries_for_export():
    """Fetch all entry data for export."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM entries ORDER BY created_at DESC").fetchall()
    entries = [dict(row) for row in rows]
    _attach_emotions_and_tags(conn, entries)
    conn.close()
    return entries


def search_entries(query):
    """Keyword search across entry content and summary."""
    conn = get_connection()
    pattern = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM entries
           WHERE content LIKE ? OR summary LIKE ?
           ORDER BY created_at DESC""",
        (pattern, pattern),
    ).fetchall()
    entries = [dict(row) for row in rows]
    _attach_emotions_and_tags(conn, entries)
    conn.close()
    return entries


@cached(ttl_seconds=60)
def get_entry_count():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    conn.close()
    return count


def get_dataset_hash(date_from=None, date_to=None):
    """Generate a hash representing the state of entries in a date range.

    Used for caching analysis results. Returns a string.
    """
    where_sql, params = _build_filter_clauses(date_from=date_from, date_to=date_to)
    conn = get_connection()
    try:
        # Get count and max modification time
        row = conn.execute(
            f"SELECT COUNT(*), MAX(modified_at) FROM entries e WHERE {where_sql}",
            params
        ).fetchone()
        count = row[0]
        last_mod = row[1] or ""
        return f"{count}_{last_mod}_{date_from}_{date_to}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Emotions CRUD
# ---------------------------------------------------------------------------


def add_emotion(entry_id, emotion, intensity="medium", frequency=0.5):
    """Add an emotion to an entry."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO emotions (entry_id, emotion, intensity, frequency) VALUES (?, ?, ?, ?)",
        (entry_id, emotion, intensity, frequency),
    )
    conn.commit()
    conn.close()


def set_emotions(entry_id, emotions):
    """Replace all emotions for an entry.

    Args:
        emotions: list of dicts with keys: emotion, intensity, frequency
    """
    conn = get_connection()
    conn.execute("DELETE FROM emotions WHERE entry_id = ?", (entry_id,))
    for em in emotions:
        conn.execute(
            "INSERT INTO emotions (entry_id, emotion, intensity, frequency) VALUES (?, ?, ?, ?)",
            (
                entry_id,
                em["emotion"],
                em.get("intensity", "medium"),
                em.get("frequency", 0.5),
            ),
        )
    conn.commit()
    conn.close()


def get_emotions_by_entry(entry_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emotions WHERE entry_id = ? ORDER BY frequency DESC",
        (entry_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tags CRUD
# ---------------------------------------------------------------------------


def add_tag(entry_id, tag_name):
    conn = get_connection()
    conn.execute(
        "INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)",
        (entry_id, tag_name.strip().lower()),
    )
    conn.commit()
    conn.close()


def set_tags(entry_id, tag_names):
    """Replace all tags for an entry."""
    conn = get_connection()
    conn.execute("DELETE FROM tags WHERE entry_id = ?", (entry_id,))
    for name in tag_names:
        name = name.strip().lower()
        if name:
            conn.execute(
                "INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)",
                (entry_id, name),
            )
    conn.commit()
    conn.close()


def get_tags_by_entry(entry_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT tag_name FROM tags WHERE entry_id = ?", (entry_id,)
    ).fetchall()
    conn.close()
    return [r["tag_name"] for r in rows]


# ---------------------------------------------------------------------------
# Smart Tag System - Tag Definitions & Aliases
# ---------------------------------------------------------------------------


def get_or_create_tag_def(tag_name, tag_type='auto', description=None):
    """Get existing tag definition or create a new one."""
    tag_name = tag_name.strip().lower().replace(' ', '-')
    if not tag_name or len(tag_name) > 30:
        return None

    conn = get_connection()
    try:
        # Check if exists
        row = conn.execute(
            "SELECT id FROM tag_defs WHERE tag_name = ?", (tag_name,)
        ).fetchone()

        if row:
            tag_id = row["id"]
            # Update last_used_at
            conn.execute(
                "UPDATE tag_defs SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                (tag_id,)
            )
            conn.commit()
            return tag_id

        # Create new
        cursor = conn.execute(
            """INSERT INTO tag_defs (tag_name, tag_type, description, is_active)
               VALUES (?, ?, ?, 1)""",
            (tag_name, tag_type, description)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def resolve_tag_alias(tag_name):
    """Resolve an alias to its canonical tag name."""
    tag_name = tag_name.strip().lower().replace(' ', '-')
    if not tag_name:
        return None

    conn = get_connection()
    try:
        # Check for alias
        row = conn.execute(
            """SELECT td.tag_name
               FROM tag_aliases ta
               JOIN tag_defs td ON ta.canonical_tag_id = td.id
               WHERE ta.alias = ? AND td.is_active = 1""",
            (tag_name,)
        ).fetchone()

        if row:
            return row["tag_name"]

        # Check for exact match
        row = conn.execute(
            "SELECT tag_name FROM tag_defs WHERE tag_name = ? AND is_active = 1",
            (tag_name,)
        ).fetchone()

        return row["tag_name"] if row else tag_name
    finally:
        conn.close()


def add_tag_alias(alias, canonical_tag_name):
    """Add an alias mapping to a canonical tag."""
    alias = alias.strip().lower().replace(' ', '-')
    canonical_tag_name = canonical_tag_name.strip().lower().replace(' ', '-')

    if alias == canonical_tag_name:
        return False

    conn = get_connection()
    try:
        # Get canonical tag id
        row = conn.execute(
            "SELECT id FROM tag_defs WHERE tag_name = ?", (canonical_tag_name,)
        ).fetchone()

        if not row:
            return False

        canonical_id = row["id"]

        # Check if alias already exists
        existing = conn.execute(
            "SELECT 1 FROM tag_aliases WHERE alias = ?", (alias,)
        ).fetchone()

        if existing:
            # Update to new canonical
            conn.execute(
                "UPDATE tag_aliases SET canonical_tag_id = ? WHERE alias = ?",
                (canonical_id, alias)
            )
        else:
            conn.execute(
                "INSERT INTO tag_aliases (alias, canonical_tag_id) VALUES (?, ?)",
                (alias, canonical_id)
            )

        conn.commit()
        return True
    finally:
        conn.close()


def get_all_tag_defs(tag_type=None, limit=None):
    """Get all tag definitions, optionally filtered by type."""
    conn = get_connection()
    try:
        sql = "SELECT * FROM tag_defs WHERE is_active = 1"
        params = []

        if tag_type:
            sql += " AND tag_type = ?"
            params.append(tag_type)

        sql += " ORDER BY last_used_at DESC NULLS LAST, created_at DESC"

        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def deactivate_tag_def(tag_name):
    """Deactivate a tag definition (mark as inactive)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE tag_defs SET is_active = 0 WHERE tag_name = ?",
            (tag_name,)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Smart Tag System - Baustellen (Curated Ongoing Concerns)
# ---------------------------------------------------------------------------


def create_baustelle(headline, core_problem=None, recent_development=None,
                     status='stable', urgency=3, is_pinned=0, is_auto_generated=1):
    """Create a new Baustelle."""
    import re
    # Generate slug from headline
    slug = re.sub(r'[^\w\s-]', '', headline.lower())
    slug = re.sub(r'\s+', '-', slug)
    slug = slug[:50]

    conn = get_connection()
    try:
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while conn.execute("SELECT 1 FROM baustellen WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1

        cursor = conn.execute(
            """INSERT INTO baustellen
               (headline, slug, core_problem, recent_development, status, urgency,
                is_pinned, is_auto_generated, created_at, last_mentioned_at, entry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)""",
            (headline, slug, core_problem, recent_development, status, urgency,
             is_pinned, is_auto_generated)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_baustelle(baustelle_id):
    """Get a single Baustelle by ID with its tags."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM baustellen WHERE id = ?", (baustelle_id,)
        ).fetchone()

        if not row:
            return None

        baustelle = dict(row)

        # Get linked tags
        tag_rows = conn.execute(
            """SELECT td.tag_name, bt.weight, bt.is_primary
               FROM baustelle_tags bt
               JOIN tag_defs td ON bt.tag_id = td.id
               WHERE bt.baustelle_id = ?
               ORDER BY bt.is_primary DESC, bt.weight DESC""",
            (baustelle_id,)
        ).fetchall()

        baustelle["tags"] = [dict(r) for r in tag_rows]
        return baustelle
    finally:
        conn.close()


def get_all_baustellen(status=None, include_inactive=False, order_by='pinned_first'):
    """Get all Baustellen, optionally filtered."""
    conn = get_connection()
    try:
        sql = "SELECT * FROM baustellen WHERE 1=1"
        params = []

        if status:
            sql += " AND status = ?"
            params.append(status)
        elif not include_inactive:
            sql += " AND status != 'closed'"

        if order_by == 'pinned_first':
            sql += " ORDER BY is_pinned DESC, urgency DESC, last_mentioned_at DESC"
        elif order_by == 'urgency':
            sql += " ORDER BY urgency DESC, last_mentioned_at DESC"
        else:
            sql += " ORDER BY last_mentioned_at DESC"

        rows = conn.execute(sql, params).fetchall()

        # Attach tags
        baustellen = []
        for row in rows:
            b = dict(row)
            tag_rows = conn.execute(
                """SELECT td.tag_name, bt.weight, bt.is_primary
                   FROM baustelle_tags bt
                   JOIN tag_defs td ON bt.tag_id = td.id
                   WHERE bt.baustelle_id = ?
                   ORDER BY bt.is_primary DESC, bt.weight DESC""",
                (b["id"],)
            ).fetchall()
            b["tags"] = [r["tag_name"] for r in tag_rows]
            baustellen.append(b)

        return baustellen
    finally:
        conn.close()


def update_baustelle(baustelle_id, **kwargs):
    """Update Baustelle fields. Allowed: headline, core_problem, recent_development,
    status, urgency, is_pinned."""
    allowed = {'headline', 'core_problem', 'recent_development', 'status', 'urgency', 'is_pinned'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return False

    conn = get_connection()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values()) + [baustelle_id]

        conn.execute(
            f"UPDATE baustellen SET {set_clause} WHERE id = ?",
            params
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def delete_baustelle(baustelle_id):
    """Delete a Baustelle (cascades to baustelle_tags and entry_baustellen)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM baustellen WHERE id = ?", (baustelle_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def link_tag_to_baustelle(baustelle_id, tag_name, weight=1.0, is_primary=False):
    """Link a tag to a Baustelle."""
    tag_id = get_or_create_tag_def(tag_name, tag_type='baustelle')
    if not tag_id:
        return False

    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO baustelle_tags
               (baustelle_id, tag_id, weight, is_primary)
               VALUES (?, ?, ?, ?)""",
            (baustelle_id, tag_id, weight, 1 if is_primary else 0)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def unlink_tag_from_baustelle(baustelle_id, tag_name):
    """Remove a tag link from a Baustelle."""
    conn = get_connection()
    try:
        conn.execute(
            """DELETE FROM baustelle_tags
               WHERE baustelle_id = ? AND tag_id IN
               (SELECT id FROM tag_defs WHERE tag_name = ?)""",
            (baustelle_id, tag_name)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def link_entry_to_baustelle(entry_id, baustelle_id, confidence=0.5, link_source='auto'):
    """Link an entry to a Baustelle."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO entry_baustellen
               (entry_id, baustelle_id, confidence, link_source)
               VALUES (?, ?, ?, ?)""",
            (entry_id, baustelle_id, confidence, link_source)
        )

        # Update entry_count and last_mentioned_at
        conn.execute(
            """UPDATE baustellen
               SET entry_count = (SELECT COUNT(DISTINCT entry_id) FROM entry_baustellen WHERE baustelle_id = ?),
                   last_mentioned_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (baustelle_id, baustelle_id)
        )

        conn.commit()
        return True
    finally:
        conn.close()


def unlink_entry_from_baustelle(entry_id, baustelle_id):
    """Remove an entry link from a Baustelle."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM entry_baustellen WHERE entry_id = ? AND baustelle_id = ?",
            (entry_id, baustelle_id)
        )

        # Update entry_count
        conn.execute(
            """UPDATE baustellen
               SET entry_count = (SELECT COUNT(DISTINCT entry_id) FROM entry_baustellen WHERE baustelle_id = ?)
               WHERE id = ?""",
            (baustelle_id, baustelle_id)
        )

        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_baustellen_for_entry(entry_id):
    """Get all Baustellen linked to an entry."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT b.*, eb.confidence, eb.link_source
               FROM baustellen b
               JOIN entry_baustellen eb ON b.id = eb.baustelle_id
               WHERE eb.entry_id = ?
               ORDER BY eb.confidence DESC, b.urgency DESC""",
            (entry_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entries_for_baustelle(baustelle_id, limit=20):
    """Get entries linked to a Baustelle."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT e.id, e.created_at, e.content, e.summary, eb.confidence
               FROM entries e
               JOIN entry_baustellen eb ON e.id = eb.entry_id
               WHERE eb.baustelle_id = ?
               ORDER BY e.created_at DESC
               LIMIT ?""",
            (baustelle_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_baustellen_by_tags(tag_names, min_match=1):
    """Find Baustellen that have matching tags."""
    if not tag_names:
        return []

    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in tag_names)
        rows = conn.execute(
            f"""SELECT b.id, b.headline, b.slug, b.status, b.urgency, COUNT(*) as match_count
                FROM baustellen b
                JOIN baustelle_tags bt ON b.id = bt.baustelle_id
                JOIN tag_defs td ON bt.tag_id = td.id
                WHERE td.tag_name IN ({placeholders}) AND b.status != 'closed'
                GROUP BY b.id
                HAVING match_count >= ?
                ORDER BY match_count DESC, b.urgency DESC""",
            tag_names + [min_match]
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def dismiss_baustellen_suggestion(pattern_slug):
    """Record that a user dismissed a pattern suggestion."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO dismissed_baustellen_suggestions (pattern_slug, dismissed_count, dismissed_at)
               VALUES (?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(pattern_slug) DO UPDATE SET
                   dismissed_count = dismissed_count + 1,
                   dismissed_at = CURRENT_TIMESTAMP""",
            (pattern_slug,)
        )
        conn.commit()
    finally:
        conn.close()


def get_dismissed_baustellen_slugs():
    """Return list of pattern slugs the user has dismissed."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT pattern_slug FROM dismissed_baustellen_suggestions"
        ).fetchall()
        return [r["pattern_slug"] for r in rows]
    finally:
        conn.close()


def get_recent_entries_for_pattern_analysis(limit=20, exclude_id=None):
    """Get recent entries with content and tags for Baustellen pattern analysis."""
    conn = get_connection()
    try:
        params = []
        sql = """SELECT e.id, e.created_at, e.content, e.summary,
                        GROUP_CONCAT(t.tag_name, ', ') as tags
                 FROM entries e
                 LEFT JOIN tags t ON e.id = t.entry_id"""
        if exclude_id:
            sql += " WHERE e.id != ?"
            params.append(exclude_id)
        sql += " GROUP BY e.id ORDER BY e.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "date": r["created_at"][:10] if r["created_at"] else "",
                "content": r["content"][:400] if r["content"] else "",
                "tags": r["tags"] or "",
                "summary": r["summary"] or "",
            })
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Frameworks CRUD
# ---------------------------------------------------------------------------


def get_framework(framework_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM frameworks WHERE id = ?", (framework_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    fw = dict(row)
    fw["questions"] = _normalize_questions(json.loads(fw["questions"]))
    return fw


def get_all_frameworks():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM frameworks ORDER BY category, name").fetchall()
    conn.close()
    frameworks = []
    for r in rows:
        fw = dict(r)
        fw["questions"] = _normalize_questions(json.loads(fw["questions"]))
        frameworks.append(fw)
    return frameworks


def create_framework(name, description, questions, category):
    normalized_questions = _normalize_questions(questions)
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO frameworks (name, description, questions, category, is_builtin) VALUES (?, ?, ?, ?, 0)",
        (name, description, json.dumps(normalized_questions), category),
    )
    fid = cursor.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_framework(framework_id, name, description, questions, category):
    """Update a user-created framework. Built-in frameworks cannot be modified."""
    normalized_questions = _normalize_questions(questions)
    conn = get_connection()
    conn.execute(
        "UPDATE frameworks SET name=?, description=?, questions=?, category=? WHERE id=? AND is_builtin=0",
        (name, description, json.dumps(normalized_questions), category, framework_id),
    )
    conn.commit()
    conn.close()


def delete_framework(framework_id):
    """Delete a user-created framework. Returns error if linked entries exist or is built-in."""
    conn = get_connection()
    row = conn.execute("SELECT is_builtin FROM frameworks WHERE id=?", (framework_id,)).fetchone()
    if row is None:
        conn.close()
        return {"error": "Framework not found."}
    if row["is_builtin"]:
        conn.close()
        return {"error": "Built-in frameworks cannot be deleted."}
    entry_count = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE framework_id=?", (framework_id,)
    ).fetchone()[0]
    if entry_count > 0:
        conn.close()
        return {"error": f"Cannot delete: {entry_count} entr{'y' if entry_count == 1 else 'ies'} use this framework."}
    conn.execute("DELETE FROM frameworks WHERE id=? AND is_builtin=0", (framework_id,))
    conn.commit()
    conn.close()
    return {}


# ---------------------------------------------------------------------------
# Embeddings CRUD
# ---------------------------------------------------------------------------


def save_embedding(entry_id, vector, model_version=""):
    """Upsert an embedding for an entry."""
    conn = get_connection()
    conn.execute("DELETE FROM embeddings WHERE entry_id = ?", (entry_id,))
    conn.execute(
        "INSERT INTO embeddings (entry_id, embedding_vector, model_version) VALUES (?, ?, ?)",
        (entry_id, json.dumps(vector), model_version),
    )
    conn.commit()
    conn.close()


def get_embedding(entry_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM embeddings WHERE entry_id = ?", (entry_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    emb = dict(row)
    emb["embedding_vector"] = json.loads(emb["embedding_vector"])
    return emb


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------


def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def get_all_settings():
    """Return all settings as a dict."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def set_settings_bulk(settings):
    """Upsert multiple settings at once."""
    if not settings:
        return
    conn = get_connection()
    conn.executemany(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        [(key, value) for key, value in settings.items()],
    )
    conn.commit()
    conn.close()


def delete_all_entries_data():
    """Delete all entries and related data (emotions, tags, embeddings)."""
    conn = get_connection()
    conn.execute("DELETE FROM entries")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Daily Questions CRUD
# ---------------------------------------------------------------------------


def get_daily_question(date=None):
    """Get the daily question for a specific date.

    Args:
        date: Date string in YYYY-MM-DD format. Defaults to today.

    Returns:
        Dict with keys: id, date, question_text, is_answered, created_at
        or None if no question exists for that date
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM daily_questions WHERE date = ?", (date,)
        ).fetchone()
        if row:
            result = dict(row)
            result["is_answered"] = bool(result["is_answered"])
            return result
        return None
    finally:
        conn.close()


def create_daily_question(date, question_text):
    """Create a daily question for a specific date.

    Args:
        date: Date string in YYYY-MM-DD format
        question_text: The question text

    Returns:
        The new question ID, or None if creation failed (e.g., duplicate date)
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO daily_questions (date, question_text) VALUES (?, ?)",
            (date, question_text),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Duplicate date - question already exists
        log.warning("Daily question already exists for date %s", date)
        return None
    finally:
        conn.close()


def mark_daily_question_answered(date=None, answered=True):
    """Mark a daily question as answered or unanswered.

    Args:
        date: Date string in YYYY-MM-DD format. Defaults to today.
        answered: Boolean indicating whether the question was answered
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE daily_questions SET is_answered = ? WHERE date = ?",
            (1 if answered else 0, date),
        )
        conn.commit()
    finally:
        conn.close()


def replace_daily_question(date, question_text):
    """Replace the daily question for a specific date.

    Deletes any existing question for the date and inserts a new one.
    Used by the "Neue Frage" button to regenerate questions.

    Args:
        date: Date string in YYYY-MM-DD format
        question_text: The new question text

    Returns:
        The new question ID
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM daily_questions WHERE date = ?", (date,))
        cursor = conn.execute(
            "INSERT INTO daily_questions (date, question_text) VALUES (?, ?)",
            (date, question_text),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def has_previous_entries():
    """Check if there are entries from dates before today.

    Used to determine if we can generate a personalized daily question.

    Returns:
        True if at least one entry exists from a previous date
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE DATE(created_at) < ?", (today,)
        ).fetchone()
        return row[0] > 0 if row else False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def get_random_prompt(category=None):
    conn = get_connection()
    if category:
        prompt = conn.execute(
            "SELECT * FROM prompts WHERE category = ? ORDER BY RANDOM() LIMIT 1",
            (category,),
        ).fetchone()
    else:
        prompt = conn.execute(
            "SELECT * FROM prompts ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    conn.close()
    return prompt


def get_random_prompts(count=3):
    """Return multiple random prompts from distinct categories."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM prompts ORDER BY RANDOM() LIMIT ?", (count,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


@cached(ttl_seconds=60)
def get_streak():
    """Calculate the current journaling streak (consecutive days with entries).

    Counts backwards from today. A day with at least one entry counts.
    Returns 0 if no entries exist.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT DATE(created_at) as d FROM entries ORDER BY d DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    from datetime import date, timedelta

    today = date.today()
    dates = set()
    for r in rows:
        try:
            dates.add(date.fromisoformat(r["d"]))
        except (ValueError, TypeError):
            continue

    # Start from today (or yesterday if no entry today yet)
    check = today
    if check not in dates:
        check = today - timedelta(days=1)
        if check not in dates:
            return 0

    streak = 0
    while check in dates:
        streak += 1
        check -= timedelta(days=1)
    return streak


@cached(ttl_seconds=60)
def get_top_emotion():
    """Return the most frequently logged emotion across all entries,
    or None if no emotions exist."""
    conn = get_connection()
    row = conn.execute(
        """SELECT emotion, COUNT(*) as cnt
           FROM emotions
           GROUP BY emotion
           ORDER BY cnt DESC
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if row:
        return {"emotion": row["emotion"], "count": row["cnt"]}
    return None


@cached(ttl_seconds=60)
def get_popular_tags(limit=10):
    """Return the most-used tag names with counts."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT tag_name, COUNT(*) as cnt
           FROM tags
           GROUP BY tag_name
           ORDER BY cnt DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"tag": r["tag_name"], "count": r["cnt"]} for r in rows]


@cached(ttl_seconds=60)
def get_total_words():
    """Return the sum of word_count across all entries."""
    conn = get_connection()
    row = conn.execute("SELECT COALESCE(SUM(word_count), 0) as total FROM entries").fetchone()
    conn.close()
    return row["total"]


# ---------------------------------------------------------------------------
# Insights data
# ---------------------------------------------------------------------------


def get_emotion_timeline(range_days=30):
    """Return per-day emotion frequencies across a date range."""
    conn = get_connection()
    start = f"-{int(range_days)} day"
    rows = conn.execute(
        """
        SELECT DATE(entries.created_at) as day, emotions.emotion as emotion,
               AVG(emotions.frequency) as avg_frequency
        FROM entries
        JOIN emotions ON entries.id = emotions.entry_id
        WHERE entries.created_at >= DATE('now', ?)
        GROUP BY day, emotions.emotion
        ORDER BY day ASC
        """,
        (start,),
    ).fetchall()
    conn.close()

    today = datetime.now().date()
    start_date = today - timedelta(days=int(range_days) - 1)
    dates = []
    cursor = start_date
    while cursor <= today:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    series = {emotion: [0.0 for _ in dates] for emotion in PLUTCHIK_EMOTIONS}
    index = {d: i for i, d in enumerate(dates)}
    for row in rows:
        day = row["day"]
        emotion = row["emotion"]
        if day in index and emotion in series:
            series[emotion][index[day]] = round(row["avg_frequency"] or 0.0, 3)

    return {
        "dates": dates,
        "series": series,
    }


def get_emotion_totals():
    """Return lifetime emotion totals for wheel visualization."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT emotion, COUNT(*) as count, AVG(frequency) as avg_frequency
        FROM emotions
        GROUP BY emotion
        """
    ).fetchall()
    conn.close()
    totals = {emotion: {"count": 0, "avg_frequency": 0.0} for emotion in PLUTCHIK_EMOTIONS}
    for row in rows:
        totals[row["emotion"]] = {
            "count": row["count"],
            "avg_frequency": round(row["avg_frequency"] or 0.0, 3),
        }
    return totals


def get_streak_calendar(range_days=90):
    """Return per-day entry counts for streak calendar."""
    conn = get_connection()
    start = f"-{int(range_days)} day"
    rows = conn.execute(
        """
        SELECT DATE(created_at) as day,
               COUNT(*) as count,
               COALESCE(SUM(word_count), 0) as words
        FROM entries
        WHERE created_at >= DATE('now', ?)
        GROUP BY day
        ORDER BY day ASC
        """,
        (start,),
    ).fetchall()
    conn.close()
    data = [
        {
            "date": row["day"],
            "count": row["count"],
            "words": row["words"],
        }
        for row in rows
    ]
    max_count = max((row["count"] for row in rows), default=0)
    return {
        "days": data,
        "max_count": max_count,
        "current_streak": get_streak(),
    }


def _top_emotion_by_entry(entry_ids):
    if not entry_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join(["?"] * len(entry_ids))
    rows = conn.execute(
        f"""
        SELECT entry_id, emotion, AVG(frequency) as avg_frequency
        FROM emotions
        WHERE entry_id IN ({placeholders})
        GROUP BY entry_id, emotion
        """,
        entry_ids,
    ).fetchall()
    conn.close()
    entries = defaultdict(list)
    for row in rows:
        entries[row["entry_id"]].append((row["emotion"], row["avg_frequency"] or 0.0))
    top = {}
    for entry_id, values in entries.items():
        values.sort(key=lambda item: item[1], reverse=True)
        top[entry_id] = values[0][0] if values else None
    return top


def get_word_cloud(range_days=365, limit=60):
    """Return word frequency data with associated emotion labels."""
    conn = get_connection()
    start = f"-{int(range_days)} day"
    rows = conn.execute(
        """
        SELECT id, content
        FROM entries
        WHERE created_at >= DATE('now', ?)
        ORDER BY created_at DESC
        LIMIT 300
        """,
        (start,),
    ).fetchall()
    conn.close()

    entry_ids = [row["id"] for row in rows]
    top_emotions = _top_emotion_by_entry(entry_ids)

    stop_words = {
        "the", "and", "for", "with", "that", "this", "was", "were", "are", "but",
        "you", "your", "about", "what", "when", "where", "which", "have", "had",
        "from", "they", "them", "then", "there", "into", "out", "over", "under",
        "just", "like", "felt", "feel", "really", "very", "been", "also", "than",
        "today", "yesterday", "tomorrow", "because", "while", "still", "after",
        "before", "would", "could", "should", "cant", "dont", "did", "does",
        "its", "im", "ive", "ill", "were", "was", "is", "am", "be", "to", "of",
        "in", "on", "at", "as", "it", "a", "an", "or", "if", "so", "we", "my",
        "me", "our", "us", "their", "his", "her", "he", "she", "i", "myself",
    }

    word_counts = Counter()
    word_emotions = defaultdict(Counter)
    token_re = re.compile(r"[A-Za-z']{3,}")

    for row in rows:
        content = row["content"] or ""
        entry_id = row["id"]
        emotion = top_emotions.get(entry_id)
        tokens = token_re.findall(content)
        for token in tokens:
            word = token.lower().strip("'")
            if len(word) < 3 or word in stop_words:
                continue
            word_counts[word] += 1
            if emotion:
                word_emotions[word][emotion] += 1

    most_common = word_counts.most_common(limit)
    words = []
    for word, count in most_common:
        emotion = None
        if word in word_emotions and word_emotions[word]:
            emotion = word_emotions[word].most_common(1)[0][0]
        words.append({"word": word, "count": count, "emotion": emotion})

    return {"words": words}


def get_framework_usage():
    """Return framework usage stats for charts."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT f.id, f.name, f.category,
               COUNT(e.id) as count,
               AVG(e.word_count) as avg_word_count,
               AVG(e.writing_duration) as avg_duration
        FROM frameworks f
        LEFT JOIN entries e ON e.framework_id = f.id
        GROUP BY f.id
        ORDER BY count DESC, f.name ASC
        """
    ).fetchall()
    category_rows = conn.execute(
        """
        SELECT f.category as category, COUNT(e.id) as count
        FROM frameworks f
        LEFT JOIN entries e ON e.framework_id = f.id
        GROUP BY f.category
        ORDER BY count DESC
        """
    ).fetchall()
    conn.close()

    frameworks = [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "count": row["count"],
            "avg_word_count": round(row["avg_word_count"] or 0.0, 1),
            "avg_duration": round((row["avg_duration"] or 0.0) / 60.0, 1),
        }
        for row in rows
    ]
    categories = [
        {"category": row["category"], "count": row["count"]}
        for row in category_rows
    ]
    return {"frameworks": frameworks, "categories": categories}


def get_writing_habits(range_days=180):
    """Return time-of-day, entry types, and duration distributions."""
    conn = get_connection()
    start = f"-{int(range_days)} day"

    hour_rows = conn.execute(
        """
        SELECT strftime('%H', created_at) as hour, COUNT(*) as count
        FROM entries
        WHERE created_at >= DATE('now', ?)
        GROUP BY hour
        """,
        (start,),
    ).fetchall()
    type_rows = conn.execute(
        """SELECT entry_type, COUNT(*) as count
           FROM entries
           WHERE created_at >= DATE('now', ?)
           GROUP BY entry_type""",
        (start,),
    ).fetchall()
    weekly_rows = conn.execute(
        """
        SELECT strftime('%Y-%W', created_at) as week,
               AVG(word_count) as avg_words,
               AVG(writing_duration) as avg_duration
        FROM entries
        WHERE created_at >= DATE('now', ?)
        GROUP BY week
        ORDER BY week ASC
        """,
        (start,),
    ).fetchall()
    duration_rows = conn.execute(
        """
        SELECT writing_duration
        FROM entries
        WHERE created_at >= DATE('now', ?)
        """,
        (start,),
    ).fetchall()
    conn.close()

    buckets = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
    for row in hour_rows:
        hour = int(row["hour"]) if row["hour"] is not None else 0
        if 5 <= hour <= 11:
            buckets["morning"] += row["count"]
        elif 12 <= hour <= 16:
            buckets["afternoon"] += row["count"]
        elif 17 <= hour <= 20:
            buckets["evening"] += row["count"]
        else:
            buckets["night"] += row["count"]

    entry_types = {row["entry_type"]: row["count"] for row in type_rows}

    week_labels = []
    avg_words = []
    avg_duration = []
    for row in weekly_rows:
        week_labels.append(row["week"])
        avg_words.append(round(row["avg_words"] or 0.0, 1))
        avg_duration.append(round((row["avg_duration"] or 0.0) / 60.0, 1))

    duration_buckets = {
        "under_5": 0,
        "five_15": 0,
        "fifteen_30": 0,
        "over_30": 0,
    }
    for row in duration_rows:
        minutes = (row["writing_duration"] or 0) / 60.0
        if minutes < 5:
            duration_buckets["under_5"] += 1
        elif minutes < 15:
            duration_buckets["five_15"] += 1
        elif minutes < 30:
            duration_buckets["fifteen_30"] += 1
        else:
            duration_buckets["over_30"] += 1

    return {
        "time_of_day": {
            "labels": ["Morning", "Afternoon", "Evening", "Night"],
            "counts": [buckets["morning"], buckets["afternoon"], buckets["evening"], buckets["night"]],
        },
        "entry_types": {
            "labels": list(entry_types.keys()),
            "counts": list(entry_types.values()),
        },
        "word_count": {
            "labels": week_labels,
            "averages": avg_words,
            "durations": avg_duration,
        },
        "duration_buckets": {
            "labels": ["<5m", "5-15m", "15-30m", "30m+"],
            "counts": [
                duration_buckets["under_5"],
                duration_buckets["five_15"],
                duration_buckets["fifteen_30"],
                duration_buckets["over_30"],
            ],
        },
    }


def get_trends(range_days=180):
    """Return sentiment and growth trends derived from emotions and tags."""
    conn = get_connection()
    start = f"-{int(range_days)} day"

    sentiment_rows = conn.execute(
        """
        SELECT DATE(entries.created_at) as day,
               SUM(CASE WHEN emotions.emotion IN ('joy', 'trust', 'anticipation')
                        THEN emotions.frequency ELSE 0 END) as pos,
               SUM(CASE WHEN emotions.emotion IN ('fear', 'sadness', 'anger', 'disgust')
                        THEN emotions.frequency ELSE 0 END) as neg,
               COUNT(DISTINCT entries.id) as entry_count
        FROM entries
        JOIN emotions ON entries.id = emotions.entry_id
        WHERE entries.created_at >= DATE('now', ?)
        GROUP BY day
        ORDER BY day ASC
        """,
        (start,),
    ).fetchall()

    gratitude_total = conn.execute(
        """
        SELECT COUNT(DISTINCT entries.id) as count
        FROM entries
        LEFT JOIN tags ON tags.entry_id = entries.id
        LEFT JOIN frameworks ON frameworks.id = entries.framework_id
        WHERE tags.tag_name = 'gratitude' OR frameworks.category = 'gratitude'
        """
    ).fetchone()

    gratitude_monthly = conn.execute(
        """
        SELECT strftime('%Y-%m', entries.created_at) as month,
               COUNT(DISTINCT entries.id) as count
        FROM entries
        LEFT JOIN tags ON tags.entry_id = entries.id
        LEFT JOIN frameworks ON frameworks.id = entries.framework_id
        WHERE tags.tag_name = 'gratitude' OR frameworks.category = 'gratitude'
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()

    total_entries = conn.execute("SELECT COUNT(*) as count FROM entries").fetchone()

    reflection_rows = conn.execute(
        """
        SELECT strftime('%Y-%W', created_at) as week,
               AVG(word_count) as avg_words,
               AVG(writing_duration) as avg_duration
        FROM entries
        WHERE created_at >= DATE('now', ?)
        GROUP BY week
        ORDER BY week ASC
        """,
        (start,),
    ).fetchall()
    conn.close()

    sentiment_labels = []
    sentiment_scores = []
    for row in sentiment_rows:
        sentiment_labels.append(row["day"])
        entry_count = row["entry_count"] or 1
        score = (row["pos"] - row["neg"]) / entry_count
        sentiment_scores.append(round(score, 3))

    gratitude_total_count = gratitude_total["count"] if gratitude_total else 0
    total_count = total_entries["count"] if total_entries else 0
    gratitude_percent = round((gratitude_total_count / total_count) * 100, 1) if total_count else 0.0

    gratitude_monthly_data = [
        {"month": row["month"], "count": row["count"]}
        for row in gratitude_monthly
    ]

    reflection_labels = []
    reflection_scores = []
    for row in reflection_rows:
        reflection_labels.append(row["week"])
        avg_words = row["avg_words"] or 0.0
        avg_duration = (row["avg_duration"] or 0.0) / 60.0
        score = avg_words * 0.4 + avg_duration * 2.0
        reflection_scores.append(round(score, 2))

    return {
        "sentiment": {"labels": sentiment_labels, "scores": sentiment_scores},
        "gratitude": {
            "total": gratitude_total_count,
            "percent": gratitude_percent,
            "monthly": gratitude_monthly_data,
        },
        "reflection": {"labels": reflection_labels, "scores": reflection_scores},
        "notes": {
            "cognitive_distortions": "not_tracked",
        },
    }


# ---------------------------------------------------------------------------
# Sample data for testing
# ---------------------------------------------------------------------------


def insert_sample_data():
    """Populate the database with sample entries, emotions, and tags for testing."""
    conn = get_connection()

    samples = [
        {
            "content": (
                "Today was a breakthrough day at work. I finally solved the "
                "authentication bug that's been haunting the team for two weeks. "
                "The issue was a race condition in the token refresh logic. Feeling "
                "incredibly accomplished and relieved. My manager noticed and gave "
                "me a shoutout in standup."
            ),
            "entry_type": "text",
            "writing_duration": 420,
            "summary": "Solved a major auth bug at work, feeling accomplished",
            "emotions": [
                {"emotion": "joy", "intensity": "high", "frequency": 0.8},
                {"emotion": "trust", "intensity": "medium", "frequency": 0.5},
                {"emotion": "surprise", "intensity": "low", "frequency": 0.3},
            ],
            "tags": ["work", "programming", "achievement"],
        },
        {
            "content": (
                "I've been feeling overwhelmed by everything lately. The project "
                "deadlines keep shifting, and I can't seem to find a rhythm. Maybe "
                "I need to step back and re-evaluate my priorities. Talked to Sarah "
                "about it and she suggested time-blocking, which sounds worth trying."
            ),
            "entry_type": "text",
            "writing_duration": 300,
            "summary": "Feeling overwhelmed by shifting deadlines, considering new strategies",
            "emotions": [
                {"emotion": "fear", "intensity": "medium", "frequency": 0.6},
                {"emotion": "sadness", "intensity": "low", "frequency": 0.4},
                {"emotion": "trust", "intensity": "medium", "frequency": 0.3},
            ],
            "tags": ["stress", "work", "self-improvement"],
        },
        {
            "content": (
                "Morning walk through the park was exactly what I needed. The cherry "
                "blossoms are in full bloom and the air smelled incredible. I sat on "
                "my favourite bench for 20 minutes just watching people go by. "
                "Reminded me that slowing down is not the same as falling behind."
            ),
            "entry_type": "text",
            "writing_duration": 240,
            "summary": "Peaceful morning walk, appreciating nature and stillness",
            "emotions": [
                {"emotion": "joy", "intensity": "medium", "frequency": 0.7},
                {"emotion": "trust", "intensity": "high", "frequency": 0.6},
                {"emotion": "anticipation", "intensity": "low", "frequency": 0.2},
            ],
            "tags": ["mindfulness", "nature", "self-care"],
        },
        {
            "content": (
                "Had a difficult conversation with Mom today about boundaries. "
                "She didn't take it well at first, but by the end I think she "
                "understood where I was coming from. I'm proud of myself for "
                "speaking up even though my voice was shaking the entire time."
            ),
            "entry_type": "voice",
            "writing_duration": 180,
            "summary": "Set boundaries with Mom, difficult but necessary conversation",
            "emotions": [
                {"emotion": "fear", "intensity": "high", "frequency": 0.5},
                {"emotion": "anger", "intensity": "low", "frequency": 0.3},
                {"emotion": "joy", "intensity": "medium", "frequency": 0.4},
                {"emotion": "trust", "intensity": "medium", "frequency": 0.5},
            ],
            "tags": ["family", "boundaries", "courage"],
        },
        {
            "content": (
                "Situation: Colleague took credit for my idea in a meeting.\n"
                "Automatic thoughts: I'm invisible. Nobody values my contributions.\n"
                "Emotions: Anger (75), Sadness (60)\n"
                "Evidence for: They did present my idea without mentioning me.\n"
                "Evidence against: My manager emailed me afterward saying she knew "
                "it was my work. Other colleagues have credited me before.\n"
                "Balanced thought: This was one incident with one person. My work "
                "is generally recognised, and I can address this directly."
            ),
            "entry_type": "framework",
            "framework_id": 3,  # CBT Thought Record
            "writing_duration": 600,
            "summary": "CBT analysis of feeling unrecognised at work",
            "emotions": [
                {"emotion": "anger", "intensity": "high", "frequency": 0.7},
                {"emotion": "sadness", "intensity": "medium", "frequency": 0.6},
                {"emotion": "disgust", "intensity": "low", "frequency": 0.3},
            ],
            "tags": ["work", "cbt", "relationships"],
        },
    ]

    entry_ids = []
    for sample in samples:
        entry_id = _new_id()
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO entries
               (id, created_at, modified_at, content, word_count, writing_duration,
                entry_type, framework_id, summary, artwork_path, artwork_style)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                now,
                now,
                sample["content"],
                _word_count(sample["content"]),
                sample["writing_duration"],
                sample["entry_type"],
                sample.get("framework_id"),
                sample.get("summary"),
                None,
                None,
            ),
        )
        for em in sample.get("emotions", []):
            conn.execute(
                "INSERT INTO emotions (entry_id, emotion, intensity, frequency) VALUES (?, ?, ?, ?)",
                (entry_id, em["emotion"], em["intensity"], em["frequency"]),
            )
        for tag in sample.get("tags", []):
            conn.execute(
                "INSERT INTO tags (entry_id, tag_name) VALUES (?, ?)",
                (entry_id, tag),
            )
        entry_ids.append(entry_id)

    conn.commit()
    conn.close()
    return entry_ids


# ---------------------------------------------------------------------------
# Database health and backup utilities
# ---------------------------------------------------------------------------


def check_database_integrity():
    """Run SQLite integrity check on the database.

    Returns:
        dict with 'ok' boolean and 'message' string
    """
    try:
        conn = get_connection()
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        is_ok = result[0] == "ok"
        return {
            "ok": is_ok,
            "message": result[0] if not is_ok else "Database integrity check passed",
        }
    except Exception as e:
        log.error("Integrity check failed: %s", e)
        return {"ok": False, "message": f"Integrity check failed: {str(e)}"}


def get_database_stats():
    """Get database statistics for diagnostics.

    Returns:
        dict with table counts and file info
    """
    try:
        conn = get_connection()

        stats = {
            "file_path": Config.DATABASE_PATH,
            "file_exists": os.path.exists(Config.DATABASE_PATH),
            "file_size_bytes": 0,
            "tables": {},
        }

        if stats["file_exists"]:
            stats["file_size_bytes"] = os.path.getsize(Config.DATABASE_PATH)
            stats["file_size_mb"] = round(stats["file_size_bytes"] / (1024 * 1024), 2)

        # Count rows in each table
        tables = ["entries", "emotions", "tags", "embeddings", "frameworks", "prompts", "settings"]
        for table in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats["tables"][table] = count
            except sqlite3.OperationalError:
                stats["tables"][table] = None  # Table doesn't exist

        conn.close()
        return stats

    except Exception as e:
        log.error("Failed to get database stats: %s", e)
        return {"error": str(e)}


def create_backup(backup_path: Optional[str] = None) -> dict:
    """Create a backup of the database.

    Args:
        backup_path: Optional path for the backup file. If not provided,
                     creates a timestamped backup in the same directory.

    Returns:
        dict with 'success' boolean, 'path' string, and 'message' string
    """
    import shutil

    if not os.path.exists(Config.DATABASE_PATH):
        return {
            "success": False,
            "path": None,
            "message": "Database file does not exist",
        }

    if backup_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.dirname(Config.DATABASE_PATH)
        backup_path = os.path.join(backup_dir, f"journal_backup_{timestamp}.db")

    try:
        # Ensure we have a clean backup by using SQLite's backup API
        conn = get_connection()
        backup_conn = sqlite3.connect(backup_path)

        conn.backup(backup_conn)

        backup_conn.close()
        conn.close()

        backup_size = os.path.getsize(backup_path)
        log.info("Database backed up to %s (%.2f MB)", backup_path, backup_size / (1024 * 1024))

        return {
            "success": True,
            "path": backup_path,
            "message": f"Backup created successfully ({backup_size / (1024 * 1024):.2f} MB)",
        }

    except Exception as e:
        log.error("Backup failed: %s", e)
        return {
            "success": False,
            "path": None,
            "message": f"Backup failed: {str(e)}",
        }


def get_backup_restore_guide() -> str:
    """Return instructions for backup and restore procedures."""
    return f"""
Database Backup and Restore Guide
=================================

Current Database Location: {Config.DATABASE_PATH}

BACKUP PROCEDURE:
1. Using the app: Settings > Export > JSON (includes all data)
2. Manual backup: Copy the database file while the app is stopped
   - Windows: copy "{Config.DATABASE_PATH}" "journal_backup.db"
   - Mac/Linux: cp "{Config.DATABASE_PATH}" "journal_backup.db"

RESTORE PROCEDURE:
1. Stop the application
2. Rename current database: mv journal.db journal.db.old
3. Copy backup: cp journal_backup.db journal.db
4. Restart the application

CORRUPTION RECOVERY:
1. Check integrity: sqlite3 journal.db "PRAGMA integrity_check"
2. If corrupted, try recovery:
   - sqlite3 journal.db ".dump" > recovery.sql
   - sqlite3 new_journal.db < recovery.sql
3. If recovery fails, restore from most recent backup

CHROMADB VECTOR STORE:
Location: {Config.CHROMA_PATH}
- Can be safely deleted and rebuilt (entries will be re-indexed)
- Delete the folder and restart to rebuild from scratch
"""


def apply_data_retention():
    """Delete entries older than the configured retention period.

    Reads the 'data_retention' setting and deletes entries that exceed the
    retention period. Called at startup.

    Returns:
        dict with 'deleted_count' and 'retention_policy'
    """
    from datetime import datetime, timedelta

    retention = get_setting("data_retention", "forever")
    if retention == "forever" or not retention:
        return {"deleted_count": 0, "retention_policy": "forever"}

    # Calculate cutoff date
    if retention == "1year":
        cutoff_days = 365
    elif retention == "2years":
        cutoff_days = 730
    else:
        return {"deleted_count": 0, "retention_policy": retention}

    cutoff_date = (datetime.now() - timedelta(days=cutoff_days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        # Get count of entries to delete
        count_result = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE created_at < ?",
            (cutoff_date,)
        ).fetchone()
        count = count_result[0] if count_result else 0

        if count > 0:
            # Delete old entries (cascades to emotions, tags, embeddings)
            conn.execute("DELETE FROM entries WHERE created_at < ?", (cutoff_date,))
            conn.commit()
            log.info("Data retention: deleted %d entries older than %s", count, cutoff_date)
            invalidate_cache()

        return {"deleted_count": count, "retention_policy": retention}

    except Exception as e:
        log.error("Data retention cleanup failed: %s", e)
        return {"deleted_count": 0, "retention_policy": retention, "error": str(e)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tag Suggestion Utilities
# ---------------------------------------------------------------------------


def get_user_tags_with_frequency(days=90, limit=50):
    """Get user's tags with usage frequency for suggestion ranking.

    Args:
        days: Number of days to look back (default 90)
        limit: Maximum tags to return (default 50)

    Returns:
        List of dicts with keys: tag_name, count, last_used
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT 
                t.tag_name,
                COUNT(*) as count,
                MAX(e.created_at) as last_used
            FROM tags t
            JOIN entries e ON t.entry_id = e.id
            WHERE e.created_at >= date('now', '-{} days')
            GROUP BY t.tag_name
            ORDER BY count DESC, last_used DESC
            LIMIT ?
            """.format(days),
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_similar_entries_by_tags(entry_id, tags, exclude_entry_id=None, limit=5):
    """Find entries with similar tag combinations.

    Args:
        entry_id: Reference entry ID
        tags: List of tags to match
        exclude_entry_id: Entry to exclude from results
        limit: Maximum entries to return

    Returns:
        List of entry IDs with similarity scores
    """
    if not tags:
        return []

    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in tags)
        exclude_clause = "AND e.id != ?" if exclude_entry_id else ""
        exclude_params = [exclude_entry_id] if exclude_entry_id else []

        rows = conn.execute(
            f"""
            SELECT 
                e.id,
                COUNT(DISTINCT t.tag_name) as matching_tags,
                GROUP_CONCAT(DISTINCT t2.tag_name) as all_tags
            FROM entries e
            JOIN tags t ON e.id = t.entry_id AND t.tag_name IN ({placeholders})
            LEFT JOIN tags t2 ON e.id = t2.entry_id
            WHERE 1=1 {exclude_clause}
            GROUP BY e.id
            HAVING matching_tags >= 1
            ORDER BY matching_tags DESC, e.created_at DESC
            LIMIT ?
            """,
            tags + exclude_params + [limit]
        ).fetchall()

        return [
            {
                "entry_id": r["id"],
                "matching_tags": r["matching_tags"],
                "all_tags": r["all_tags"].split(",") if r["all_tags"] else []
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_tag_cooccurrences(min_cooccurrence=2, limit=30):
    """Find tags that frequently appear together.

    Args:
        min_cooccurrence: Minimum number of co-occurrences (default 2)
        limit: Maximum pairs to return

    Returns:
        List of dicts with keys: tag1, tag2, co_occurrence
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT 
                t1.tag_name as tag1,
                t2.tag_name as tag2,
                COUNT(*) as co_occurrence
            FROM tags t1
            JOIN tags t2 ON t1.entry_id = t2.entry_id AND t1.tag_name < t2.tag_name
            GROUP BY t1.tag_name, t2.tag_name
            HAVING co_occurrence >= ?
            ORDER BY co_occurrence DESC
            LIMIT ?
            """,
            (min_cooccurrence, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_tag_trends(tag_name, days=30):
    """Get usage trend for a specific tag.

    Args:
        tag_name: Tag to analyze
        days: Number of days to analyze

    Returns:
        Dict with usage stats and trend
    """
    conn = get_connection()
    try:
        # Get daily counts
        rows = conn.execute(
            """
            SELECT 
                date(e.created_at) as day,
                COUNT(*) as count
            FROM tags t
            JOIN entries e ON t.entry_id = e.id
            WHERE t.tag_name = ?
                AND e.created_at >= date('now', '-? days')
            GROUP BY date(e.created_at)
            ORDER BY day
            """,
            (tag_name, days)
        ).fetchall()

        total = sum(r["count"] for r in rows)
        days_with_usage = len(rows)

        return {
            "tag": tag_name,
            "total_uses": total,
            "days_with_usage": days_with_usage,
            "average_per_day": round(total / days, 2) if days > 0 else 0,
            "daily_breakdown": [dict(r) for r in rows]
        }
    finally:
        conn.close()
