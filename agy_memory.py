#!/usr/bin/env python3
"""
AGY Memory Engine - Standalone Dynamic Memory Component
SQLite FTS5 + Multilingual Keywords + Typo/Fuzzy Search + Cached Model Resolution
"""

import sys
import os
import sqlite3
import argparse
import re
import subprocess
import json
import difflib

DB_PATH = os.path.expanduser("~/.gemini/memory.db")
CACHE_PATH = os.path.expanduser("~/.gemini/memory_model_cache.txt")
DEFAULT_MODEL = "gemini-3.7-flash-high"

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

def get_db():
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
    return conn

def get_existing_keys() -> list:
    conn = get_db()
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
        res = subprocess.run(["/home/ubuntu/.local/bin/agy", "models"], capture_output=True, text=True, timeout=10)
        lines = res.stdout.splitlines()
        for line in lines:
            parts = line.strip().split()
            if parts and ("flash" in parts[0].lower() or "gemini" in parts[0].lower()):
                model_id = parts[0]
                try:
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
    """Retrieve all indexed vocabulary tokens from memories for fast fuzzy/typo correction."""
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

    conn = get_db()
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
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM memories WHERE id = ?", (fact_id,))
    cursor.execute("DELETE FROM memories_fts WHERE id = ?", (fact_id,))
    
    cursor.execute("""
        INSERT INTO memories (id, category, fact, keywords, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (fact_id, category, fact, keywords))
    
    cursor.execute("""
        INSERT INTO memories_fts (id, category, fact, keywords)
        VALUES (?, ?, ?, ?)
    """, (fact_id, category, fact, keywords))
    
    conn.commit()

def list_memories():
    conn = get_db()
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
            ["/home/ubuntu/.local/bin/agy", "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
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
                ["/home/ubuntu/.local/bin/agy", "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
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
        facts = json.loads(json_match.group(0))
        for item in facts:
            if "id" in item and "fact" in item:
                upsert_fact(item["id"], item.get("category", "general"), item["fact"], item.get("keywords", ""))
                print(f"Memory synced via {model_name}: {item['id']}")

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

    subparsers.add_parser("list")

    args = parser.parse_args()

    if args.command == "prefetch":
        prefetch(args.query)
    elif args.command == "sync-turn":
        sync_turn(args.user, args.assistant)
    elif args.command == "add":
        upsert_fact(args.id, args.category, args.fact, args.keywords)
        print(f"Added memory {args.id}")
    elif args.command == "list":
        list_memories()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
