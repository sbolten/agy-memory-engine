# AGY Memory Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Lightweight, high-performance, standalone dynamic memory layer for Google Antigravity (`agy`) and autonomous agent frameworks.

Inspired by Hermes Agent's 3-pillar memory architecture, using SQLite FTS5 for ultra-fast local retrieval (<2ms) and autonomous LLM background extraction for continuous long-term learning without prompt bloat.

---

## 🌟 Key Features

- **⚡ Blazing Fast Retrieval (<2ms):** Uses native SQLite FTS5 full-text indexing with BM25 ranking.
- **🔍 Typo & Fuzzy Fallback:** Automatically handles misspelled terms and queries via `difflib` vocabulary matching.
- **🌐 Multilingual & German/English Stopword Filtering:** Filters out noise and matches keywords cross-lingually.
- **🧠 Zero External Dependencies:** Pure Python 3 standard library (`sqlite3`, `re`, `difflib`, `argparse`, `json`, `subprocess`).
- **🔌 Dual Interface:**
  - **CLI:** `prefetch`, `sync-turn`, `add`, `list` for shell scripts, cron jobs, and custom gateway integrations.
  - **MCP Server:** Standard Model Context Protocol (`agy_memory_mcp.py`) exposing `search_memory`, `store_memory`, and `list_memories`.
- **⚙️ Configurable & Portable:** Resolves `agy` from `$PATH` automatically; database and cache paths configurable via environment variables (`AGY_MEMORY_DB`, `AGY_MEMORY_CACHE`, `AGY_BIN`).

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (standard library only, no `pip install` required)
- Google Antigravity CLI (`agy`) installed in `$PATH` or `~/.local/bin/agy` (optional, needed for automated `sync-turn`)

### 2. Manual Fact Management (CLI)
```bash
# Add a fact
python3 agy_memory.py add --id "user.timezone" --category "preference" --fact "Timezone is Europe/Zurich (CET/CEST)" --keywords "timezone zeit zeitzone zurich schweiz"

# List stored memories
python3 agy_memory.py list

# Query / Prefetch context for an upcoming prompt
python3 agy_memory.py prefetch "Wann beginnt das Meeting in Zürich?"
```

### 3. Dynamic Conversation Turn Syncing
Pass user input and assistant response to extract and persist new facts asynchronously:
```bash
python3 agy_memory.py sync-turn --user "Remember that our staging server IP changed to 192.168.1.150" --assistant "Understood, updated the staging IP."
```

---

## 🔌 Model Context Protocol (MCP) Setup

To connect the memory engine directly to AGY or any MCP-compatible agent, register the server in your MCP settings:

```json
{
  "mcpServers": {
    "memory": {
      "command": "python3",
      "args": ["/path/to/agy-memory-engine/agy_memory_mcp.py"],
      "env": {
        "AGY_MEMORY_DB": "~/.gemini/memory.db"
      }
    }
  }
}
```

---

## 📄 License

MIT License © 2026 Stephan Bolten
