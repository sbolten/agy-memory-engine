#!/usr/bin/env python3
"""
AGY Memory Engine - Multi-Layer Cognitive Memory Component
- Layer 1: Semantic Fact-Store (SQLite FTS5: IPs, configs, hardware, master data)
- Layer 2: Narrative & Episodic Store (Themen-Dossiers, Chroniken, Beziehungsdynamiken, Verläufe)
- Layer 3: Experiential & Learnings Store (Erkenntnisse, Heuristiken, Urteile, Haltungen)
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
    "schau", "sag", "zeig", "prüfe", "checke", "bitte", "mal", "uns", "unsere", "ihr", "ihre",
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

    # 1. Memories Table (Atomic Facts)
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

    # 2. Episodes Table (Narrative Chronicles, Context, Stances)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            period TEXT,
            status TEXT DEFAULT 'active',
            narrative TEXT NOT NULL,
            entities TEXT,
            stance TEXT,
            keywords TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
            id, topic, title, narrative, entities, stance, keywords
        );
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_episodes_ai AFTER INSERT ON episodes BEGIN
            INSERT INTO episodes_fts (id, topic, title, narrative, entities, stance, keywords)
            VALUES (new.id, new.topic, new.title, new.narrative, new.entities, new.stance, new.keywords);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_episodes_ad AFTER DELETE ON episodes BEGIN
            DELETE FROM episodes_fts WHERE id = old.id;
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_episodes_au AFTER UPDATE ON episodes BEGIN
            DELETE FROM episodes_fts WHERE id = old.id;
            INSERT INTO episodes_fts (id, topic, title, narrative, entities, stance, keywords)
            VALUES (new.id, new.topic, new.title, new.narrative, new.entities, new.stance, new.keywords);
        END;
    """)

    # 3. Learnings Table (Experiential Heuristics, Practical Insights)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learnings (
            id TEXT PRIMARY KEY,
            category TEXT,
            insight TEXT NOT NULL,
            context TEXT,
            keywords TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS learnings_fts USING fts5(
            id, category, insight, context, keywords
        );
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_learnings_ai AFTER INSERT ON learnings BEGIN
            INSERT INTO learnings_fts (id, category, insight, context, keywords)
            VALUES (new.id, new.category, new.insight, new.context, new.keywords);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_learnings_ad AFTER DELETE ON learnings BEGIN
            DELETE FROM learnings_fts WHERE id = old.id;
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_learnings_au AFTER UPDATE ON learnings BEGIN
            DELETE FROM learnings_fts WHERE id = old.id;
            INSERT INTO learnings_fts (id, category, insight, context, keywords)
            VALUES (new.id, new.category, new.insight, new.context, new.keywords);
        END;
    """)

    try:
        yield conn
    finally:
        conn.close()

def get_existing_database_inventory() -> dict:
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM memories")
        fact_keys = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT id, title, topic FROM episodes")
        episode_keys = [{"id": row[0], "title": row[1], "topic": row[2]} for row in cursor.fetchall()]
        cursor.execute("SELECT id, category FROM learnings")
        learning_keys = [{"id": row[0], "category": row[1]} for row in cursor.fetchall()]
        return {
            "fact_keys": fact_keys,
            "episodes": episode_keys,
            "learnings": learning_keys
        }

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
    """Retrieve indexed vocabulary tokens from all tables for fast fuzzy/typo correction."""
    vocab = set()
    cursor.execute("SELECT id, category, fact, keywords FROM memories")
    for fid, cat, fact, kws in cursor.fetchall():
        tokens = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]{4,}', f"{fid} {cat or ''} {fact} {kws or ''}".lower())
        vocab.update(tokens)
    
    cursor.execute("SELECT id, topic, title, narrative, entities, stance, keywords FROM episodes")
    for row in cursor.fetchall():
        text = " ".join([str(x) for x in row if x])
        tokens = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]{4,}', text.lower())
        vocab.update(tokens)

    cursor.execute("SELECT id, category, insight, context, keywords FROM learnings")
    for row in cursor.fetchall():
        text = " ".join([str(x) for x in row if x])
        tokens = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]{4,}', text.lower())
        vocab.update(tokens)

    return vocab

def prefetch(query: str, limit_facts: int = 3, limit_episodes: int = 2, limit_learnings: int = 2):
    if is_trivial_prompt(query):
        return

    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Always load persistent preferences and rules
        cursor.execute("""
            SELECT id, category, fact 
            FROM memories 
            WHERE category IN ('preference', 'rule', 'preferences')
            ORDER BY id ASC
        """)
        pref_rows = cursor.fetchall()
        seen_fact_ids = {r[0] for r in pref_rows}

        # 2. Extract search terms
        raw_words = re.findall(r'[a-zA-Z0-9äöüÄÖÜß]+', query.lower())
        words = [w for w in raw_words if len(w) > 2 and w not in STOPWORDS]

        fact_rows = []
        episode_rows = []
        learning_rows = []

        if words:
            fts_terms = [f'"{w}"*' if len(w) >= 4 else f'"{w}"' for w in words]
            fts_query = " OR ".join(fts_terms)

            # Query Memories FTS
            try:
                cursor.execute("""
                    SELECT m.id, m.category, m.fact 
                    FROM memories m
                    JOIN memories_fts f ON m.id = f.id
                    WHERE memories_fts MATCH ?
                    ORDER BY f.rank
                    LIMIT ?;
                """, (fts_query, limit_facts + len(seen_fact_ids)))
                for r in cursor.fetchall():
                    if r[0] not in seen_fact_ids and r[1] not in ('preference', 'rule', 'preferences'):
                        fact_rows.append(r)
                        seen_fact_ids.add(r[0])
                        if len(fact_rows) >= limit_facts:
                            break
            except sqlite3.OperationalError:
                fact_rows = []

            # Query Episodes FTS via JOIN
            try:
                cursor.execute("""
                    SELECT e.id, e.topic, e.title, e.period, e.status, e.narrative, e.entities, e.stance 
                    FROM episodes e
                    JOIN episodes_fts f ON e.id = f.id
                    WHERE episodes_fts MATCH ?
                    ORDER BY f.rank
                    LIMIT ?;
                """, (fts_query, limit_episodes))
                episode_rows = cursor.fetchall()
            except sqlite3.OperationalError:
                episode_rows = []

            # Query Learnings FTS via JOIN
            try:
                cursor.execute("""
                    SELECT l.id, l.category, l.insight, l.context 
                    FROM learnings l
                    JOIN learnings_fts f ON l.id = f.id
                    WHERE learnings_fts MATCH ?
                    ORDER BY f.rank
                    LIMIT ?;
                """, (fts_query, limit_learnings))
                learning_rows = cursor.fetchall()
            except sqlite3.OperationalError:
                learning_rows = []

            # Fuzzy / Typo Fallback if no matching results found
            if not fact_rows and not episode_rows and any(len(w) >= 4 for w in words):
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
                            SELECT m.id, m.category, m.fact 
                            FROM memories m
                            JOIN memories_fts f ON m.id = f.id
                            WHERE memories_fts MATCH ?
                            ORDER BY f.rank
                            LIMIT ?;
                        """, (fuzzy_fts, limit_facts + len(seen_fact_ids)))
                        for r in cursor.fetchall():
                            if r[0] not in seen_fact_ids and r[1] not in ('preference', 'rule', 'preferences'):
                                fact_rows.append(r)
                                seen_fact_ids.add(r[0])
                                if len(fact_rows) >= limit_facts:
                                    break
                    except sqlite3.OperationalError:
                        pass

                    try:
                        cursor.execute("""
                            SELECT e.id, e.topic, e.title, e.period, e.status, e.narrative, e.entities, e.stance 
                            FROM episodes e
                            JOIN episodes_fts f ON e.id = f.id
                            WHERE episodes_fts MATCH ?
                            ORDER BY f.rank
                            LIMIT ?;
                        """, (fuzzy_fts, limit_episodes))
                        episode_rows = cursor.fetchall()
                    except sqlite3.OperationalError:
                        pass

        # Output Generation
        total_facts = pref_rows + fact_rows
        if total_facts or episode_rows or learning_rows:
            if total_facts:
                print("[🧠 Memory Context - Facts]")
                for _, cat, fact in total_facts:
                    prefix = f"({cat}) " if cat else ""
                    print(f"• {prefix}{fact}")

            if episode_rows:
                print("\n[📖 Narrative Context - Episodic Memory]")
                for eid, topic, title, period, status, narrative, entities, stance in episode_rows:
                    period_str = f" | {period}" if period else ""
                    status_str = f" | {status}" if status else ""
                    print(f"• [{title}{period_str}{status_str}]")
                    print(f"  Kontext: {narrative}")
                    if stance:
                        print(f"  Haltung/Stance: {stance}")
                    if entities:
                        print(f"  Beteiligte/Entitäten: {entities}")

            if learning_rows:
                print("\n[💡 Learnings & Heuristics]")
                for lid, cat, insight, context in learning_rows:
                    prefix = f"({cat}) " if cat else ""
                    ctx_str = f" [Kontext: {context}]" if context else ""
                    print(f"• {prefix}{insight}{ctx_str}")

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

def upsert_episode(episode_id: str, topic: str, title: str, narrative: str, period: str = "", status: str = "active", entities: str = "", stance: str = "", keywords: str = ""):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO episodes (id, topic, title, period, status, narrative, entities, stance, keywords, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                topic = excluded.topic,
                title = excluded.title,
                period = excluded.period,
                status = excluded.status,
                narrative = excluded.narrative,
                entities = excluded.entities,
                stance = excluded.stance,
                keywords = excluded.keywords,
                updated_at = CURRENT_TIMESTAMP;
        """, (episode_id, topic, title, period, status, narrative, entities, stance, keywords))
        conn.commit()

def upsert_learning(learning_id: str, category: str, insight: str, context: str = "", keywords: str = ""):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO learnings (id, category, insight, context, keywords, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                category = excluded.category,
                insight = excluded.insight,
                context = excluded.context,
                keywords = excluded.keywords,
                updated_at = CURRENT_TIMESTAMP;
        """, (learning_id, category, insight, context, keywords))
        conn.commit()

def list_all():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, fact FROM memories ORDER BY category, id")
        facts = cursor.fetchall()
        cursor.execute("SELECT id, topic, title, period, status, narrative, stance FROM episodes ORDER BY topic, id")
        episodes = cursor.fetchall()
        cursor.execute("SELECT id, category, insight, context FROM learnings ORDER BY category, id")
        learnings = cursor.fetchall()

        print("=" * 80)
        print(f"SEMANTIC FACTS ({len(facts)})")
        print("=" * 80)
        for fid, cat, fact in facts:
            print(f"{fid:<25} | {(cat or ''):<12} | {fact}")

        print("\n" + "=" * 80)
        print(f"NARRATIVE CHRONICLES & EPISODES ({len(episodes)})")
        print("=" * 80)
        for eid, topic, title, period, status, narrative, stance in episodes:
            p_str = f" ({period})" if period else ""
            s_str = f" [{status}]" if status else ""
            print(f"\n▶ [{eid}] {title}{p_str}{s_str} (Topic: {topic})")
            print(f"  Narrative: {narrative}")
            if stance:
                print(f"  Stance:    {stance}")

        print("\n" + "=" * 80)
        print(f"EXPERIENTIAL LEARNINGS & HEURISTICS ({len(learnings)})")
        print("=" * 80)
        for lid, cat, insight, context in learnings:
            ctx = f" (Context: {context})" if context else ""
            print(f"{lid:<25} | {(cat or ''):<12} | {insight}{ctx}")

def sync_turn(user_prompt: str, assistant_response: str):
    if is_trivial_prompt(user_prompt):
        return

    inv = get_existing_database_inventory()
    inv_context = json.dumps(inv, ensure_ascii=False, indent=2)

    prompt = f"""You are the Multi-Layer Cognitive Memory Engine for Stephan Bolten.
Analyze the conversation turn below and extract any persistent information across THREE distinct layers:

1. ATOMIC FACTS ("facts"): Hard facts, IP addresses, specs, master data, device IDs, account names, medications, configuration parameters, definite dates.
2. NARRATIVE CHRONICLES & EPISODES ("episodes"): Background histories, disputes, social/relationship dynamics, sentiment/stances towards people/topics, multi-event story arcs, context over time.
3. EXPERIENTIAL LEARNINGS ("learnings"): Practical insights, rules of thumb, lessons learned from past actions, subjective opinions or tested heuristics.

Existing Database Keys & Topics:
{inv_context}

RULES:
- If updating an existing item from the inventory above, reuse its exact ID.
- Keep facts atomic and dense.
- Keep narrative episodes rich with context, background, and user stance (3-5 comprehensive sentences).
- Always include multilingual keywords (German/English synonyms, misspellings, related query terms).
- If NOTHING persistent or new was revealed in a category, leave its array empty.

User: {user_prompt}
Assistant: {assistant_response}

Output ONLY a single valid JSON object in this exact schema (or {{"facts":[], "episodes":[], "learnings":[]}} if none):
{{
  "facts": [
    {{
      "id": "...",
      "category": "...",
      "fact": "...",
      "keywords": "..."
    }}
  ],
  "episodes": [
    {{
      "id": "...",
      "topic": "...",
      "title": "...",
      "period": "...",
      "status": "active|historic|resolved",
      "narrative": "...",
      "entities": "...",
      "stance": "...",
      "keywords": "..."
    }}
  ],
  "learnings": [
    {{
      "id": "...",
      "category": "...",
      "insight": "...",
      "context": "...",
      "keywords": "..."
    }}
  ]
}}
"""

    model_name = get_cached_model()
    out = ""

    try:
        res = subprocess.run(
            [AGY_BIN, "--print", prompt, "--model", model_name, "--dangerously-skip-permissions"],
            capture_output=True, text=True, timeout=90
        )
        out = res.stdout.strip()
    except Exception:
        out = ""

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

    if not out:
        return

    json_match = re.search(r'\{.*\}', out, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict):
                # Facts
                for f in data.get("facts", []):
                    if isinstance(f, dict) and "id" in f and "fact" in f:
                        upsert_fact(f["id"], f.get("category", "general"), f["fact"], f.get("keywords", ""))
                        print(f"Fact synced: {f['id']}")
                # Episodes
                for ep in data.get("episodes", []):
                    if isinstance(ep, dict) and "id" in ep and "narrative" in ep:
                        upsert_episode(
                            ep["id"],
                            ep.get("topic", "general"),
                            ep.get("title", ep["id"]),
                            ep["narrative"],
                            period=ep.get("period", ""),
                            status=ep.get("status", "active"),
                            entities=ep.get("entities", ""),
                            stance=ep.get("stance", ""),
                            keywords=ep.get("keywords", "")
                        )
                        print(f"Episode synced: {ep['id']}")
                # Learnings
                for lr in data.get("learnings", []):
                    if isinstance(lr, dict) and "id" in lr and "insight" in lr:
                        upsert_learning(
                            lr["id"],
                            lr.get("category", "general"),
                            lr["insight"],
                            context=lr.get("context", ""),
                            keywords=lr.get("keywords", "")
                        )
                        print(f"Learning synced: {lr['id']}")
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON decode error during memory sync: {e}\n")
        except Exception as e:
            sys.stderr.write(f"Unexpected error during memory sync: {e}\n")

def compact_all(apply_changes: bool = False):
    """Compacts and optimizes all SQLite tables, runs VACUUM and rebuilds FTS indexes."""
    backup_dir = os.path.expanduser("~/.gemini/archive")
    os.makedirs(backup_dir, exist_ok=True)
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"memory_db_backup_{ts}.bak")
    shutil.copy2(DB_PATH, backup_file)
    print(f"[BACKUP] Snapshot created: {backup_file}")

    with db_session() as conn:
        print("[OPTIMIZE] Rebuilding FTS5 indexes...")
        conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild');")
        conn.execute("INSERT INTO episodes_fts(episodes_fts) VALUES('rebuild');")
        conn.execute("INSERT INTO learnings_fts(learnings_fts) VALUES('rebuild');")
        conn.commit()

    conn_raw = sqlite3.connect(DB_PATH)
    conn_raw.execute("VACUUM;")
    conn_raw.close()
    print("[SUCCESS] All tables and indexes successfully rebuilt and vacuumed!")

def main():
    parser = argparse.ArgumentParser(description="AGY Multi-Layer Cognitive Memory Engine")
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

    ae = subparsers.add_parser("add-episode")
    ae.add_argument("--id", type=str, required=True)
    ae.add_argument("--topic", type=str, required=True)
    ae.add_argument("--title", type=str, required=True)
    ae.add_argument("--narrative", type=str, required=True)
    ae.add_argument("--period", type=str, default="")
    ae.add_argument("--status", type=str, default="active")
    ae.add_argument("--entities", type=str, default="")
    ae.add_argument("--stance", type=str, default="")
    ae.add_argument("--keywords", type=str, default="")

    al = subparsers.add_parser("add-learning")
    al.add_argument("--id", type=str, required=True)
    al.add_argument("--category", type=str, default="general")
    al.add_argument("--insight", type=str, required=True)
    al.add_argument("--context", type=str, default="")
    al.add_argument("--keywords", type=str, default="")

    cp = subparsers.add_parser("compact")
    cp.add_argument("--apply", action="store_true", help="Apply compaction changes")

    subparsers.add_parser("list")

    args = parser.parse_args()

    if args.command == "prefetch":
        prefetch(args.query)
    elif args.command == "sync-turn":
        sync_turn(args.user, args.assistant)
    elif args.command == "add":
        upsert_fact(args.id, args.category, args.fact, args.keywords)
        print(f"Added fact {args.id}")
    elif args.command == "add-episode":
        upsert_episode(args.id, args.topic, args.title, args.narrative, args.period, args.status, args.entities, args.stance, args.keywords)
        print(f"Added episode {args.id}")
    elif args.command == "add-learning":
        upsert_learning(args.id, args.category, args.insight, args.context, args.keywords)
        print(f"Added learning {args.id}")
    elif args.command == "compact":
        compact_all(apply_changes=args.apply)
    elif args.command == "list":
        list_all()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
