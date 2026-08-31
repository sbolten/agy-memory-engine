"""
Queue Manager for AGY Asynchronous Memory Pipeline
Handles thread-safe, fast SQLite turn queue in ~/.gemini/turn_queue.db
"""
import os
import sqlite3
import hashlib
from contextlib import contextmanager

QUEUE_DB_PATH = os.environ.get("AGY_TURN_QUEUE_DB", os.path.expanduser("~/.gemini/turn_queue.db"))

def init_queue_db(db_path: str = QUEUE_DB_PATH):
    """Ensure the turn queue table exists with WAL mode."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path, timeout=5.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turn_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE,
                source TEXT DEFAULT 'telegram',
                chat_id TEXT,
                user_prompt TEXT NOT NULL,
                assistant_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                extracted_summary TEXT,
                error TEXT
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_turn_queue_status ON turn_queue(status, id);")

def enqueue_turn(user_prompt: str, assistant_response: str, source: str = "telegram", chat_id: str = "299090858", db_path: str = QUEUE_DB_PATH) -> bool:
    """Fast non-blocking insert of a turn into the queue (< 1ms)."""
    if not user_prompt or not user_prompt.strip():
        return False

    internal_markers = [
        "Multi-Layer Cognitive Memory Engine",
        "Du bist Stephans persönlicher autonomer KI-Assistent in Zürich für das Paket",
        "PROFIL Stephan:",
        "TPA BOT REPORT",
        "STATUS-SNAPSHOT [Paket:",
        "AGY Bot Integrity Watchdog"
    ]
    if any(m in user_prompt for m in internal_markers):
        return False

    init_queue_db(db_path)
    # Deduplication hash based on prompt + response snippet
    content_hash = hashlib.sha256((user_prompt.strip() + "|||" + assistant_response[:300].strip()).encode("utf-8")).hexdigest()
    try:
        with sqlite3.connect(db_path, timeout=2.0) as conn:
            conn.execute("""
                INSERT INTO turn_queue (hash, source, chat_id, user_prompt, assistant_response, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(hash) DO NOTHING;
            """, (content_hash, source, str(chat_id) if chat_id else "299090858", user_prompt.strip(), assistant_response.strip()))
            conn.commit()
            return True
    except Exception:
        return False

def get_pending_turns(limit: int = 10, db_path: str = QUEUE_DB_PATH) -> list:
    """Fetch oldest pending turns for processing."""
    init_queue_db(db_path)
    with sqlite3.connect(db_path, timeout=5.0) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source, chat_id, user_prompt, assistant_response, created_at
            FROM turn_queue
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [{
            "id": r[0],
            "source": r[1],
            "chat_id": r[2],
            "user_prompt": r[3],
            "assistant_response": r[4],
            "created_at": r[5]
        } for r in rows]

def mark_turn_status(turn_ids: list, status: str, summary: str = None, error: str = None, db_path: str = QUEUE_DB_PATH):
    """Update status of processed turns."""
    if not turn_ids:
        return
    init_queue_db(db_path)
    with sqlite3.connect(db_path, timeout=5.0) as conn:
        placeholders = ",".join("?" for _ in turn_ids)
        conn.execute(f"""
            UPDATE turn_queue
            SET status = ?, extracted_summary = ?, error = ?
            WHERE id IN ({placeholders})
        """, [status, summary, error] + list(turn_ids))
        conn.commit()

def prune_processed_turns(days: int = 7, db_path: str = QUEUE_DB_PATH):
    """Delete old processed / skipped items."""
    init_queue_db(db_path)
    try:
        with sqlite3.connect(db_path, timeout=5.0) as conn:
            conn.execute("""
                DELETE FROM turn_queue
                WHERE status IN ('processed', 'skipped')
                  AND datetime(created_at) < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()
    except Exception:
        pass
