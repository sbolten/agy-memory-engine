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
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory")

DB_PATH = os.environ.get("AGY_MEMORY_DB", os.path.expanduser("~/.gemini/memory.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

@mcp.tool()
def search_memory(query: str, limit: int = 5) -> str:
    """Search personal persistent memories and facts by keyword.
    
    Args:
        query: Search terms or keywords to query the memory store.
        limit: Maximum number of results to return (default: 5).
    """
    conn = get_db()
    cursor = conn.cursor()
    words = [w for w in query.split() if len(w) > 2]
    if not words:
        return json.dumps([], ensure_ascii=False)
    fts_query = " OR ".join(words)
    try:
        cursor.execute("""
            SELECT id, category, fact FROM memories_fts 
            WHERE memories_fts MATCH ? LIMIT ?
        """, (fts_query, limit))
        results = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.tool()
def store_memory(id: str, fact: str, category: str = "general") -> str:
    """Store or update a persistent fact or preference.
    
    Args:
        id: Unique identifier / key for this memory.
        fact: Fact content or description.
        category: Category classification (default: general).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE id = ?", (id,))
    cursor.execute("DELETE FROM memories_fts WHERE id = ?", (id,))
    cursor.execute("INSERT INTO memories (id, category, fact) VALUES (?, ?, ?)", (id, category, fact))
    cursor.execute("INSERT INTO memories_fts (id, category, fact) VALUES (?, ?, ?)", (id, category, fact))
    conn.commit()
    return f"Successfully stored memory '{id}'"

@mcp.tool()
def list_memories() -> str:
    """List all stored personal memories."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, fact FROM memories ORDER BY updated_at DESC")
    results = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
    return json.dumps(results, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    mcp.run()
