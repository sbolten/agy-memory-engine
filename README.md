# AGY Memory Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Lightweight, high-performance, standalone dynamic memory layer for Google Antigravity (`agy`) and autonomous agent frameworks.

Inspired by Hermes Agent's 3-pillar memory architecture, using SQLite FTS5 for ultra-fast local retrieval (<2ms) and autonomous LLM background extraction for continuous long-term learning without prompt bloat.

---

## 🧩 The Big Picture: Autonomous Agent Stack (AGY + Telegram + Memory)

`agy-memory-engine` is designed as the persistent semantic backbone of a 24/7 personal autonomous agent stack:

```text
                  ┌────────────────────────────────────────┐
                  │          User on Telegram UI           │
                  │   ("Deploy staging update on prod-server") │
                  └──────────────────┬─────────────────────┘
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │    Telegram Gateway / Sidecar     │
                   └───────┬───────────────────▲───────┘
                           │                   │
               1. Pre-fetch│                   │ 5. Telegram
                 (< 2ms)   │                   │    Response
                           ▼                   │
            ┌─────────────────────────────┐    │
            │   AGY Memory Engine (FTS5)  │    │
            │   - Staging IP: 192.168.1.50│    │
            │   - SSH Port: 2222          │    │
            │   - User Prefs & Hardware   │    │
            └──────────────┬──────────────┘    │
                           │ 2. Injected       │
                           │    Ephemeral      │
                           │    Context        │
                           ▼                   │
            ┌──────────────────────────────────┴──┐
            │   Google Antigravity CLI (`agy`)    │
            │   - Autonomous Execution            │
            │   - Tool Calls / Skills / MCP       │
            │   - Multi-Turn Reasoning            │
            └──────────────┬──────────────────────┘
                           │
                           │ 3. Output Stream
                           ▼
                    ┌──────────────┐
                    │ Async Worker │ 4. Background `sync-turn`
                    │  (no delay)  │───► Extracts new facts & persists
                    └──────────────┘     into `memory.db` without blocking UI
```

---

## 🏛️ The 3-Pillar Memory Philosophy

To keep the agent razor-sharp across thousands of daily turns without prompt bloat or massive token bills, memory is partitioned into 3 distinct layers:

| Pillar | Type | Scope & Lifecycle | Storage Mechanism |
|---|---|---|---|
| **Pillar 1** | **Episodic / Working Context** | Transient day-to-day conversation, ephemeral tasks, session scratchpad. Dies after task completion or referenced via logs. | In-flight context window, Google Tasks, Transcripts |
| **Pillar 2** | **Semantic / Long-Term Facts** | Deterministic facts, server IPs, personal master data, credentials metadata, hardware specs, family profiles. Permanent & instantly searchable. | **`~/.gemini/memory.db` (SQLite FTS5 + BM25)** |
| **Pillar 3** | **Procedural / Skills & Rules** | *How* to execute tasks: API definitions, security rules, playbooks, formatting standards. | System Rules (`user_global`), AGY Skills |

---

## 💡 Why AGY Memory Engine? (Motivation & Design Decisions)

Most LLM memory solutions today suffer from two extremes:
1. **Vector DB / Semantic RAG bloat:** Embedding models, heavy C++/native dependencies (Chroma, FAISS, PyTorch), slow cold-starts, vector drift, and poor keyword/exact match (e.g. failing to cleanly recall exact IP addresses, port numbers, serials, or drug doses).
2. **Context-stuffing everything:** Relying on huge 1M–2M context windows adds massive latency, increases token costs exponentially, and dilutes the agent's attention on long-running multi-turn sessions.

### Key Insights:
- **Exact & Fast > Fuzzy Vectors for Core Facts:** When an agent needs your timezone, server IPs, hardware specs, or personal preferences, SQLite FTS5 with BM25 ranking delivers deterministic, exact results in **< 2ms** with **0 MB extra RAM**.
- **Telegram UX requires sub-second response starts:** SQLite FTS5 pre-fetches relevant facts locally via standard library Python before the LLM begins streaming.
- **Zero External Dependencies:** Built entirely on Python’s standard library (`sqlite3`, `re`, `difflib`). Runs anywhere without `pip install`, wheel compilation issues, or Docker container overhead.
- **Dynamic Pre-fetching without Prompt Bloat:** Instead of dumping an entire personal wiki into the system prompt, `agy-memory` extracts key entities, fetches only the 3–5 relevant facts, and injects them as ephemeral context.
- **Autonomous Background Learning & Compaction:** Ingesting new memories is decoupled from the user interaction (`sync-turn`). Over time, automated nightly compaction (`compact --apply`) deduplicates, resolves contradictions, and prunes stale data across all user accounts.

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
python3 agy_memory.py add --id "user.timezone" --category "preference" --fact "Timezone is UTC (CET/CEST)" --keywords "timezone zeit zeitzone time"

# List stored memories
python3 agy_memory.py list

# Query / Prefetch context for an upcoming prompt
python3 agy_memory.py prefetch "Wann beginnt das nächste Meeting?"
```

### 3. Dynamic Conversation Turn Syncing
Pass user input and assistant response to extract and persist new facts asynchronously:
```bash
python3 agy_memory.py sync-turn --user "Remember that our staging server IP changed to 192.168.1.150" --assistant "Understood, updated the staging IP."
```

### 4. Compaction, Deduplication & Knowledge Maintenance (`compact`)

Over time, continuous background learning (`sync-turn`) can accumulate overlapping facts, fragmented notes, or outdated states. The `compact` command serves as an automated knowledge curator.

#### 🎯 Why Use Memory Compaction?
- **Redundancy Elimination:** Merges scattered mentions of the same subject into single, dense canonical entries.
- **Contradiction & Drift Resolution:** Replaces superseded states (e.g. updated server IPs, new medication doses, changed configurations) while preserving current accuracy.
- **Zero Data Loss Guarantee:** Retains 100% of concrete details (exact dates, IDs, serial numbers, credentials, URLs).
- **Keyword Enrichment:** Generates fresh, multi-lingual search keywords (DE/EN synonyms and misspellings) to maximize FTS5 retrieval recall.
- **Database Optimization:** Rebuilds the FTS5 virtual table index and runs SQLite `VACUUM` to eliminate fragmentation.

```bash
# 1. Dry-run audit: Analyzes memories and displays a detailed diff/preview without writing changes
python3 agy_memory.py compact

# 2. Apply: Creates a timestamped backup in ~/.gemini/archive/, applies consolidations, and vacuums SQLite
python3 agy_memory.py compact --apply
```

---

## 👥 Multi-User Nightly Maintenance (`scripts/agy-memory-compact-all.sh`)

On multi-user servers where multiple local users (e.g. family members or team members) run independent Antigravity instances, memory databases are isolated under each user's home directory (`~/.gemini/memory.db`).

The script [`scripts/agy-memory-compact-all.sh`](scripts/agy-memory-compact-all.sh) automates maintenance across all users:

### How it works:
1. **Auto-Discovery:** Scans `/home/*` for active user accounts with an existing `~/.gemini/memory.db`.
2. **Permission Isolation:** Executes the compaction strictly within each user's own permission boundary (`su - $username`), ensuring backups and DB files retain correct ownership (`0600`/`0700`).
3. **Plug & Play for New Users:** Any newly created Linux user with an initialized memory database is automatically included without requiring manual configuration.

### Deployment via System Cron:
Create `/etc/cron.d/agy-memory-compact`:

```cron
# /etc/cron.d/agy-memory-compact
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
CRON_TZ=UTC

# Run nightly at 04:00 AM before daily system backups
0 4 * * * root /usr/local/bin/agy-memory-compact-all.sh >/dev/null 2>&1
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
