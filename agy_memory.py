#!/usr/bin/env python3
"""
AGY Memory Engine - Standalone Dynamic Memory Component
SQLite FTS5 + Multilingual Keywords + Typo/Fuzzy Search + Cached Model Resolution
"""

import sys
import os
import shutil
import sqlite3
import argparse
import re
import subprocess
import json
import difflib
from contextlib import contextmanager

DB_PATH = os.environ.get("AGY_MEMORY_DB", os.path.expanduser("~/.gemini/memory.db"))
CACHE_PATH = os.environ.get("AGY_MEMORY_CACHE", os.path.expanduser("~/.gemini/memory_model_cache.txt"))
DEFAULT_MODEL = "gemini-3.7-flash-high"
AGY_BIN = os.environ.get("AGY_BIN") or shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")

STOPWORDS = {
    "wie", "was", "wer", "wo", "wann", "warum", "welches", "welche", "welcher", "woher", "wohin",
    "ist", "sind", "war", "waren", "wird", "werden", "habe", "hat", "haben", "auf", "mit", "von",
    "aus", "für", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "einem", "einen",
    "und", "oder", "aber", "auch", "noch", "nur", "schon", "immer", "wieder", "heute", "gestern",
    "morgen", "mein", "meine", "meinen", "meiner", "meinem", "unser", "unsere", "unserem", "unseren",
    "lautet", "läuft", "geht", "bekommt", "macht", "gibt", "zeigt", "registriert", "geregelt",
    "schau", "sag", "zeig", "prüfe", "checke", "bitte",
    # English & Latin stopwords / auxiliary verbs
    "the", "and", "is", "are", "was", "were", "what", "where", "when", "how", "who", "why",
    "which", "with", "from", "for", "about", "can", "could", "would", "should", "have", "has",
    "had", "our", "my", "your", "his", "her", "their", "its", "show", "tell", "check", "find",
    "that", "this", "then", "them", "they", "been", "into", "some", "more", "most", "such",
    "est", "non", "sed", "et", "aut", "cum", "per"
}

TRIVIAL_PROMPT_RE = re.compile(
    r'^(yes|no|ok|okay|sure|thanks|thank you|y|n|yep|nope|yeah|nah|'
    r'hi|hey|hello|yo|sup|1|2|3|4|5|'
    r'continue|go ahead|do it|proceed|got it|cool|nice|great|done|next|lgtm|k)'
    r'[\s!?.:;,"' + "'" + r'~\u2018\u2019\u201c\u201d\u2014\u2013\u2026()\[\]{}<>*&^%$#@!+=`\u00a0]*$',
    re.IGNORECASE,
)

@contextmanager
def db_session():
    """Ensure directory exists and manage SQLite connection lifecycle cleanly."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            category TEXT,
            fact TEXT NOT NULL,
            keywords TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            id, category, fact, keywords
        );
    """)
    # Setup automatic triggers to keep memories_fts perfectly synced without manual dual-writes
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts (id, category, fact, keywords)
            VALUES (new.id, new.category, new.fact, new.keywords);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON memories BEGIN
            DELETE FROM memories_fts WHERE id = old.id;
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON memories BEGIN
            DELETE FROM memories_fts WHERE id = old.id;
            INSERT INTO memories_fts (id, category, fact, keywords)
            VALUES (new.id, new.category, new.fact, new.keywords);
        END;
    """)
    try:
        yield conn
    finally:
        conn.close()

def get_existing_keys() -> list:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM memories")
        return [row[0] for row in cursor.fetchall()]

def get_cached_model() -> str:
    """Read cached model from disk if available, otherwise return default."""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass
    return DEFAULT_MODEL

def discover_and_cache_latest_flash_low_model() -> str:
    """Scan agy models list for the newest Gemini Flash model and persist it to disk."""
    try:
        res = subprocess.run([AGY_BIN, "models"], capture_output=True, text=True, timeout=10)
        lines = res.stdout.splitlines()
        for line in lines:
            parts = line.strip().split()
            if parts and ("flash" in parts[0].lower() or "gemini" in parts[0].lower()):
                model_id = parts[0]
                try:
                    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
                    with open(CACHE_PATH, "w", encoding="utf-8") as f:
                        f.write(model_id)
                except Exception:
                    pass
                return model_id
    except Exception:
        pass
    return DEFAULT_MODEL

def is_trivial_prompt(text: str) -> bool:
    if not text or not text.strip():
        return True
    stripped = text.strip()
    if stripped.startswith("/"):
        return True
    return bool(TRIVIAL_PROMPT_RE.match(stripped))

def get_all_vocabulary(cursor) -> set:
    """Retrieve indexed vocabulary tokens from memories for fast fuzzy/typo correction."""
    cursor.execute("SELECT id, category, fact, keywords FROM memories")
    rows = cursor.fetchall()
    vocab = set()
    for fid, cat, fact, kws in rows:
        text = f"{fid} {cat or ''} {fact} {kws or ''}"
        tokens = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]{4,}', text.lower())
        vocab.update(tokens)
    return vocab

def prefetch(query: str, limit: int = 3):
    if is_trivial_prompt(query):
        return

    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Always load persistent preferences and rules (deterministic order for prompt cache efficiency)
        cursor.execute("""
            SELECT id, category, fact 
            FROM memories 
            WHERE category IN ('preference', 'rule')
            ORDER BY id ASC
        """)
        pref_rows = cursor.fetchall()
        seen_ids = {r[0] for r in pref_rows}

        # 2. Extract search terms for dynamic context search
        raw_words = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]+', query.lower())
        words = [w for w in raw_words if len(w) > 2 and w not in STOPWORDS]

        context_rows = []
        if words:
            # Direct FTS Query: Prefix wildcard for words >= 4 chars, exact match for short <= 3 char words
            fts_terms = [f'"{w}"*' if len(w) >= 4 else f'"{w}"' for w in words]
            fts_query = " OR ".join(fts_terms)

            try:
                cursor.execute("""
                    SELECT id, category, fact 
                    FROM memories_fts 
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                """, (fts_query, limit + len(seen_ids)))
                for r in cursor.fetchall():
                    if r[0] not in seen_ids and r[1] not in ('preference', 'rule'):
                        context_rows.append(r)
                        seen_ids.add(r[0])
                        if len(context_rows) >= limit:
                            break
            except sqlite3.OperationalError:
                context_rows = []

            # Fuzzy / Typo Fallback if no exact/prefix match found
            if not context_rows and any(len(w) >= 4 for w in words):
                vocab = get_all_vocabulary(cursor)
                corrected_words = []
                for w in words:
                    if len(w) >= 4 and w not in vocab:
                        cutoff = 0.75 if len(w) >= 5 else 0.80
                        closest = difflib.get_close_matches(w, vocab, n=1, cutoff=cutoff)
                        if closest:
                            corrected_words.append(closest[0])
                    elif w in vocab:
                        corrected_words.append(w)

                if corrected_words:
                    fuzzy_fts = " OR ".join([f'"{cw}"*' if len(cw) >= 4 else f'"{cw}"' for cw in corrected_words])
                    try:
                        cursor.execute("""
                            SELECT id, category, fact 
                            FROM memories_fts 
                            WHERE memories_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?;
                        """, (fuzzy_fts, limit + len(seen_ids)))
                        for r in cursor.fetchall():
                            if r[0] not in seen_ids and r[1] not in ('preference', 'rule'):
                                context_rows.append(r)
                                seen_ids.add(r[0])
                                if len(context_rows) >= limit:
                                    break
                    except sqlite3.OperationalError:
                        pass

        all_output_rows = pref_rows + context_rows
        if all_output_rows:
            print("[🧠 Memory Context]")
            for _, cat, fact in all_output_rows:
                prefix = f"({cat}) " if cat else ""
                print(f"• {prefix}{fact}")

def upsert_fact(fact_id: str, category: str, fact: str, keywords: str = ""):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (id, category, fact, keywords, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                category = excluded.category,
                fact = excluded.fact,
                keywords = excluded.keywords,
                updated_at = CURRENT_TIMESTAMP;
        """, (fact_id, category, fact, keywords))
        conn.commit()

def list_memories():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, fact, updated_at FROM memories ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        if not rows:
            print("No memories stored yet.")
            return
        print(f"{'ID':<25} | {'CATEGORY':<12} | {'FACT'}")
        print("-" * 75)
        for fid, cat, fact, _ in rows:
            print(f"{fid:<25} | {(cat or ''):<12} | {fact}")

def sync_turn(user_prompt: str, assistant_response: str):
    if is_trivial_prompt(user_prompt):
        return

    existing_keys = get_existing_keys()
    keys_context = f"Existing database keys: {json.dumps(existing_keys)}" if existing_keys else ""

    prompt = f"""Analyze the conversation below. If persistent personal facts, preferences, server IPs, device IDs, or configuration changes were stated/updated/cancelled, extract them.
{keys_context}
IMPORTANT: If an existing key from the database list above matches the subject (e.g. 'travel.iceland2027'), USE THAT EXACT KEY ID to update it.

Always provide multilingual search keywords (German, English, synonyms, alternative spellings, query terms) in the "keywords" field for each fact.

User: {user_prompt}
Assistant: {assistant_response}

If NO new or updated persistent facts exist, output ONLY: NONE
If facts exist, output ONLY a valid JSON array of objects with keys "id", "category", "fact", and "keywords". Example:
[
  {{
    "id": "travel.iceland2027",
    "category": "travel",
    "fact": "Island Reise 2027 wurde abgesagt wegen Budget.",
    "keywords": "Iceland Island travel trip vacation holiday Reykjavik ferien urlaub"
  }}
]
"""
    model_name = get_cached_model()
    out = ""

    # Attempt 1: Fast cached model execution with 90s timeout
    try:
        res = subprocess.run(
            [AGY_BIN, "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
            capture_output=True, text=True, timeout=90
        )
        out = res.stdout.strip()
    except Exception:
        out = ""

    # Attempt 2: If cached model failed/timed out, perform auto-discovery and retry
    if not out:
        model_name = discover_and_cache_latest_flash_low_model()
        try:
            res = subprocess.run(
                [AGY_BIN, "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
                capture_output=True, text=True, timeout=90
            )
            out = res.stdout.strip()
        except Exception as e:
            sys.stderr.write(f"Sync failed: {e}\n")
            return

    if not out or "NONE" in out:
        return

    json_match = re.search(r'\[.*\]', out, re.DOTALL)
    if json_match:
        try:
            facts = json.loads(json_match.group(0))
            if isinstance(facts, list):
                for item in facts:
                    if isinstance(item, dict) and "id" in item and "fact" in item:
                        upsert_fact(item["id"], item.get("category", "general"), item["fact"], item.get("keywords", ""))
                        print(f"Memory synced via {model_name}: {item['id']}")
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON decode error during memory sync: {e}\n")
        except Exception as e:
            sys.stderr.write(f"Unexpected error during memory sync: {e}\n")

def compact_memories(apply_changes: bool = False):
    """
    Audit all facts in memory.db for redundancies, overlapping information, and contradictions.
    Creates a timestamped backup before applying any modifications.
    Consolidates facts without data loss, updates SQLite FTS, and runs VACUUM.
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, fact, keywords FROM memories ORDER BY category, id")
        rows = cursor.fetchall()

    if not rows:
        print("No memories to compact.")
        return

    current_memories = [
        {"id": r[0], "category": r[1] or "general", "fact": r[2], "keywords": r[3] or ""}
        for r in rows
    ]

    print(f"Loaded {len(current_memories)} memories for audit & compaction...")

    prompt = f"""You are an expert data curator and fact-consolidation engine.
Analyze the following JSON list of persistent memories extracted from a user's SQLite knowledge base.

Goal:
1. Detect duplicate or semantically redundant entries (e.g. facts mentioned in multiple places or partial duplicates).
2. Detect contradictions or outdated states (if one fact supersedes another, retain the most current, accurate, comprehensive information).
3. Merge overlapping facts into clean, atomic, consolidated entries WITHOUT ANY INFORMATION LOSS.
4. Ensure hierarchical and consistent ID keys (e.g., 'user.profile', 'infra.oci', 'finance.etf').
5. Generate comprehensive multilingual keywords (German/English synonyms, misspellings, search terms) for each consolidated item.
6. Preserve all existing accurate details (names, dates, IDs, IPs, serial numbers, account info, specific parameters). DO NOT DROP ANY SPECIFIC FACTS OR DETAILS.

Input Memories:
{json.dumps(current_memories, ensure_ascii=False, indent=2)}

Output Format:
Return ONLY a valid JSON array of consolidated memory objects. Each object must have:
- "id": string (the unique canonical key)
- "category": string
- "fact": string (clear, dense, consolidated factual summary)
- "keywords": string (space-separated search terms/synonyms)

If no consolidation or deduplication is necessary and the current list is already optimal, return the exact same items.
Output JSON only:
"""

    model_name = get_cached_model()
    out = ""

    print(f"Analyzing knowledge base with {model_name}...")
    try:
        res = subprocess.run(
            [AGY_BIN, "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
            capture_output=True, text=True, timeout=120
        )
        out = res.stdout.strip()
    except Exception:
        out = ""

    if not out:
        model_name = discover_and_cache_latest_flash_low_model()
        try:
            res = subprocess.run(
                [AGY_BIN, "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
                capture_output=True, text=True, timeout=120
            )
            out = res.stdout.strip()
        except Exception as e:
            sys.stderr.write(f"Compaction analysis failed: {e}\n")
            return

    json_match = re.search(r'\[.*\]', out, re.DOTALL)
    if not json_match:
        print("Compaction error: Model did not return a valid JSON array.")
        return

    try:
        compacted = json.loads(json_match.group(0))
    except Exception as e:
        print(f"JSON parsing error: {e}")
        return

    if not isinstance(compacted, list) or len(compacted) == 0:
        print("Compaction error: Empty result.")
        return

    # Diff analysis
    old_by_id = {m["id"]: m for m in current_memories}
    new_by_id = {m["id"]: m for m in compacted}

    added = [m for m in compacted if m["id"] not in old_by_id]
    removed = [m for m in current_memories if m["id"] not in new_by_id]
    modified = [
        m for m in compacted
        if m["id"] in old_by_id and (
            old_by_id[m["id"]]["fact"] != m["fact"] or
            old_by_id[m["id"]]["category"] != m["category"]
        )
    ]
    unchanged = [
        m for m in compacted
        if m["id"] in old_by_id and (
            old_by_id[m["id"]]["fact"] == m["fact"] and
            old_by_id[m["id"]]["category"] == m["category"]
        )
    ]

    print("\n" + "=" * 60)
    print("COMPACTION AUDIT REPORT")
    print("=" * 60)
    print(f"Original entries:  {len(current_memories)}")
    print(f"Compacted entries: {len(compacted)}")
    print(f"Unchanged:         {len(unchanged)}")
    print(f"Modified/Merged:   {len(modified)}")
    print(f"New keys:          {len(added)}")
    print(f"Removed/Merged:    {len(removed)}")

    if modified:
        print("\n--- MODIFIED / CONSOLIDATED ENTRIES ---")
        for m in modified:
            old = old_by_id[m["id"]]
            print(f"\nKey: [{m['id']}] (Category: {m['category']})")
            print(f"  [-] Old: {old['fact']}")
            print(f"  [+] New: {m['fact']}")

    if removed:
        print("\n--- MERGED / REMOVED KEYS ---")
        for r in removed:
            print(f"  [-] {r['id']}: {r['fact']}")

    if added:
        print("\n--- NEW KEYS ---")
        for a in added:
            print(f"  [+] {a['id']}: {a['fact']}")

    if not apply_changes:
        print("\n" + "=" * 60)
        print("[DRY-RUN] No changes were written to database.")
        print("To apply changes, run with '--apply'.")
        print("=" * 60)
        return

    # Backup before applying
    backup_dir = os.path.expanduser("~/.gemini/archive")
    os.makedirs(backup_dir, exist_ok=True)
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"memory_db_backup_{ts}.bak")
    shutil.copy2(DB_PATH, backup_file)
    print(f"\n[BACKUP] Snapshot created: {backup_file}")

    with db_session() as conn:
        cursor = conn.cursor()
        # Atomic replace in transaction
        cursor.execute("DELETE FROM memories;")
        for item in compacted:
            cursor.execute("""
                INSERT INTO memories (id, category, fact, keywords, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);
            """, (item["id"], item.get("category", "general"), item["fact"], item.get("keywords", "")))
        conn.commit()

        # Optimize DB and rebuild FTS
        print("[OPTIMIZE] Running VACUUM and FTS5 rebuild...")
        conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild');")
        conn.commit()

    # VACUUM outside transaction
    conn_raw = sqlite3.connect(DB_PATH)
    conn_raw.execute("VACUUM;")
    conn_raw.close()

    print("[SUCCESS] Memory database successfully compacted, deduplicated, and vacuumed!")


def main():
    parser = argparse.ArgumentParser(description="AGY Standalone Memory Engine")
    subparsers = parser.add_subparsers(dest="command")

    pf = subparsers.add_parser("prefetch")
    pf.add_argument("query", type=str, help="User query text")

    st = subparsers.add_parser("sync-turn")
    st.add_argument("--user", type=str, required=True)
    st.add_argument("--assistant", type=str, required=True)

    ad = subparsers.add_parser("add")
    ad.add_argument("--id", type=str, required=True)
    ad.add_argument("--category", type=str, default="general")
    ad.add_argument("--fact", type=str, required=True)
    ad.add_argument("--keywords", type=str, default="")

    cp = subparsers.add_parser("compact")
    cp.add_argument("--apply", action="store_true", help="Apply compaction changes (default: dry-run)")

    subparsers.add_parser("list")

    args = parser.parse_args()

    if args.command == "prefetch":
        prefetch(args.query)
    elif args.command == "sync-turn":
        sync_turn(args.user, args.assistant)
    elif args.command == "add":
        upsert_fact(args.id, args.category, args.fact, args.keywords)
        print(f"Added memory {args.id}")
    elif args.command == "compact":
        compact_memories(apply_changes=args.apply)
    elif args.command == "list":
        list_memories()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

