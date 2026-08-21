#!/usr/bin/env python3
"""
AGY Memory Engine - MCP Server Layer (FastMCP)
Allows AGY to explicitly query, store, and delete memories via MCP standard.
"""

import sys
import json
import sqlite3
import os
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory")

DB_PATH = os.environ.get("AGY_MEMORY_DB", os.path.expanduser("~/.gemini/memory.db"))

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

@mcp.tool()
def search_memory(query: str, limit: int = 5) -> str:
    """Search personal persistent memories and facts by keyword.
    
    Args:
        query: Search terms or keywords to query the memory store.
        limit: Maximum number of results to return (default: 5).
    """
    words = [w for w in query.split() if len(w) > 2]
    if not words:
        return json.dumps([], ensure_ascii=False)
    fts_query = " OR ".join(words)
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, category, fact FROM memories_fts 
                WHERE memories_fts MATCH ? LIMIT ?
            """, (fts_query, limit))
            results = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
            return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.tool()
def store_memory(id: str, fact: str, category: str = "general", keywords: str = "") -> str:
    """Store or update a persistent fact or preference.
    
    Args:
        id: Unique identifier / key for this memory.
        fact: Fact content or description.
        category: Category classification (default: general).
        keywords: Optional search keywords or synonyms.
    """
    try:
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
            """, (id, category, fact, keywords))
            conn.commit()
        return f"Successfully stored memory '{id}'"
    except Exception as e:
        return f"Error storing memory: {e}"

@mcp.tool()
def list_memories() -> str:
    """List all stored personal memories."""
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, category, fact FROM memories ORDER BY updated_at DESC")
            results = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
            return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
