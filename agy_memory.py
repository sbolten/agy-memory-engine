#!/usr/bin/env python3
"""
AGY Memory Engine - Standalone Dynamic Memory Component
SQLite FTS5 + Option A (Async AGY Subagent Sync)
"""

import sys
import os
import sqlite3
import argparse
import re
import subprocess
import json

DB_PATH = os.path.expanduser("~/.gemini/memory.db")

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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            id, category, fact
        );
    """)
    return conn

def is_trivial_prompt(text: str) -> bool:
    if not text or not text.strip():
        return True
    stripped = text.strip()
    if stripped.startswith("/"):
        return True
    return bool(TRIVIAL_PROMPT_RE.match(stripped))

def prefetch(query: str, limit: int = 3):
    if is_trivial_prompt(query):
        return

    conn = get_db()
    cursor = conn.cursor()

    words = [w for w in re.findall(r'\w+', query) if len(w) > 2]
    if not words:
        return

    fts_query = " OR ".join(words)
    try:
        cursor.execute("""
            SELECT id, category, fact 
            FROM memories_fts 
            WHERE memories_fts MATCH ?
            LIMIT ?;
        """, (fts_query, limit))
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []

    if rows:
        print("[🧠 Memory Context]")
        for _, cat, fact in rows:
            prefix = f"({cat}) " if cat else ""
            print(f"• {prefix}{fact}")

def upsert_fact(fact_id: str, category: str, fact: str):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM memories WHERE id = ?", (fact_id,))
    cursor.execute("DELETE FROM memories_fts WHERE id = ?", (fact_id,))
    
    cursor.execute("""
        INSERT INTO memories (id, category, fact, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (fact_id, category, fact))
    
    cursor.execute("""
        INSERT INTO memories_fts (id, category, fact)
        VALUES (?, ?, ?)
    """, (fact_id, category, fact))
    
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

    prompt = f"""Analyze the following turn and determine if any persistent personal facts, preferences, server IPs, device IDs, or configuration changes were stated.

User: {user_prompt}
Assistant: {assistant_response}

If NO new persistent facts are present, respond with: NONE
If facts ARE present, output ONLY a valid JSON array of objects with keys "id", "category", and "fact". Example:
[
  {{"id": "hardware.beelink.ip", "category": "hardware", "fact": "Beelink Server IP is 100.114.118.47"}}
]
"""
    try:
        res = subprocess.run(
            ["/home/ubuntu/.local/bin/agy", "--print", prompt, "--model", "flash_lite"],
            capture_output=True, text=True, timeout=25
        )
        out = res.stdout.strip()
        if not out or "NONE" in out:
            return

        json_match = re.search(r'\[.*\]', out, re.DOTALL)
        if json_match:
            facts = json.loads(json_match.group(0))
            for item in facts:
                if "id" in item and "fact" in item:
                    upsert_fact(item["id"], item.get("category", "general"), item["fact"])
                    print(f"Memory synced: {item['id']}")
    except Exception as e:
        sys.stderr.write(f"Sync failed: {e}\n")

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

    subparsers.add_parser("list")

    args = parser.parse_args()

    if args.command == "prefetch":
        prefetch(args.query)
    elif args.command == "sync-turn":
        sync_turn(args.user, args.assistant)
    elif args.command == "add":
        upsert_fact(args.id, args.category, args.fact)
        print(f"Added memory {args.id}")
    elif args.command == "list":
        list_memories()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
