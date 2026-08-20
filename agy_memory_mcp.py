#!/usr/bin/env python3
"""
AGY Memory Engine - MCP Server Layer
Allows AGY to explicitly query, store, and delete memories via MCP standard.
"""

import sys
import json
import sqlite3
import os

DB_PATH = os.path.expanduser("~/.gemini/memory.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def search_memory(query, limit=5):
    conn = get_db()
    cursor = conn.cursor()
    words = [w for w in query.split() if len(w) > 2]
    if not words:
        return []
    fts_query = " OR ".join(words)
    try:
        cursor.execute("""
            SELECT id, category, fact FROM memories_fts 
            WHERE memories_fts MATCH ? LIMIT ?
        """, (fts_query, limit))
        return [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]
    except Exception:
        return []

def store_memory(fact_id, category, fact):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE id = ?", (fact_id,))
    cursor.execute("DELETE FROM memories_fts WHERE id = ?", (fact_id,))
    cursor.execute("INSERT INTO memories (id, category, fact) VALUES (?, ?, ?)", (fact_id, category, fact))
    cursor.execute("INSERT INTO memories_fts (id, category, fact) VALUES (?, ?, ?)", (fact_id, category, fact))
    conn.commit()
    return f"Successfully stored memory '{fact_id}'"

def list_memories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, fact FROM memories ORDER BY updated_at DESC")
    return [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]

def handle_mcp_request(request):
    method = request.get("method")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agy-memory-mcp", "version": "1.0.0"}
            }
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "search_memory",
                        "description": "Search personal persistent memories and facts by keyword.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "store_memory",
                        "description": "Store or update a persistent fact or preference.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "category": {"type": "string"},
                                "fact": {"type": "string"}
                            },
                            "required": ["id", "fact"]
                        }
                    },
                    {
                        "name": "list_memories",
                        "description": "List all stored personal memories.",
                        "inputSchema": {"type": "object", "properties": {}}
                    }
                ]
            }
        }
    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "search_memory":
            res = search_memory(args.get("query", ""))
            content = json.dumps(res, indent=2)
        elif name == "store_memory":
            content = store_memory(args.get("id"), args.get("category", "general"), args.get("fact"))
        elif name == "list_memories":
            res = list_memories()
            content = json.dumps(res, indent=2)
        else:
            content = "Unknown tool"

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": content}]}
        }
    return None

def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            resp = handle_mcp_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception:
            pass

if __name__ == "__main__":
    main()
