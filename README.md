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

## 🏛️ The Multi-Layer Cognitive Memory Architecture

To keep the agent razor-sharp across thousands of daily turns without prompt bloat or massive token bills, `agy-memory-engine` implements a 3-layer cognitive storage model:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ~/.gemini/memory.db                                      │
├────────────────────────────────┬────────────────────────────┬───────────────────────────────┤
│    Layer 1: Atomic Facts       │ Layer 2: Narrative Dossiers│  Layer 3: Heuristic Learnings │
│          (`memories`)          │        (`episodes`)        │         (`learnings`)         │
├────────────────────────────────┼────────────────────────────┼───────────────────────────────┤
│ - Server IPs, SSH ports        │ - Multi-turn background    │ - User preferences & stances  │
│ - Hardware IDs & serials       │   chronicles & stories     │ - Heuristics, decisions, rules│
│ - Personal master data         │ - Active projects & status │ - Operational guidelines      │
│ - Instant exact key-value match│ - Timeline-based evolution │ - Context-aware advice        │
└────────────────────────────────┴────────────────────────────┴───────────────────────────────┘
```

| Layer | Type | Scope & Lifecycle | Storage & Search Mechanism |
|---|---|---|---|
| **Layer 1** | **Atomic Semantic Facts** | Deterministic facts, server IPs, hardware specs, credentials metadata, master data. Permanent & exact. | SQLite FTS5 + BM25 (`memories` table) |
| **Layer 2** | **Narrative Episodes & Dossiers** | Multi-turn chronicles, project states, timelines, and ongoing relationship/topic context. | SQLite FTS5 + BM25 (`episodes` table) |
| **Layer 3** | **Experiential Learnings & Heuristics**| Tactical lessons, personal stances, decision rules, and cognitive heuristics. | SQLite FTS5 + BM25 (`learnings` table) |

---

## 💡 Why SQLite FTS5 vs. Vector DBs (Chroma, Qdrant, FAISS)?

A deliberate architectural choice was made to use **native SQLite FTS5 + BM25 keyword ranking** instead of traditional Vector Databases (like ChromaDB, Qdrant, Pinecone, or FAISS).

Here is why:

### 1. 🎯 Exact Recall vs. "Semantic Drift" for Hard Facts
Vector embeddings excel at semantic fuzziness (*"find things about travel"*), but they notoriously struggle with deterministic, exact-match queries:
* **Vector DB Failure Mode:** An embedding search for `"Server IP 192.168.1.50"` or `"Port 8085"` frequently retrieves `"192.168.1.51"` or unrelated network docs because numerical tokens are close in vector space.
* **SQLite FTS5 Advantage:** Exact substring, prefix (`token*`), token-level matches, and BM25 relevance guarantee that queries for specific hostnames, MAC addresses, port numbers, serials, and IDs return the exact record 100% of the time.

### 2. ⚡ Ultra-Low Latency (<2ms vs. 150-400ms)
* **Vector DBs:** Require computing a dense vector embedding via an external model (API roundtrip of ~100–300ms or local ONNX runtime overhead of 30–80ms + 200MB+ RAM).
* **SQLite FTS5:** Pure C-based B-tree / FTS5 index lookup completes in **0.8ms to 2.0ms** directly in-process via Python's built-in `sqlite3`.
* **Impact on Telegram / CLI UX:** Injects pre-fetched context instantly before the LLM begins streaming its first token.

### 3. 🪶 Zero Dependencies & Native Portability
* **Vector DBs:** Require heavyweight native C++/Rust dependencies, compilation chains (wheels for PyTorch, NumPy, ONNX, tokenizers, or running Docker containers).
* **SQLite FTS5:** **Zero external dependencies.** Built 100% on the Python 3.10+ standard library (`sqlite3`, `re`, `difflib`, `argparse`, `json`). It runs identically on minimal Linux servers, ARM single-board computers, macOS, and barebone CI runners without running `pip install`.

### 4. 🔒 Zero Hallucinated Duplication (Strict Topic Upsert)
Vector databases blindly append embedding vectors, leading to contradictory duplicates (*"Staging server is .50"* and *"Staging server is .150"* both existing forever).
* `agy-memory-engine` enforces structured `topic_key` IDs (`hardware.server.ip`). Updates deterministically overwrite the existing key, ensuring a single source of truth without knowledge drift.

### 5. 💰 Zero Embedding Model & API Costs
Embedding every message turn or background sync consumes embedding API credits or local GPU/CPU cycles. SQLite FTS5 indexes text instantly with zero computational cost.

---

## 🌟 Key Features

- **⚡ Blazing Fast Retrieval (<2ms):** Uses native SQLite FTS5 full-text indexing with BM25 ranking across all 3 cognitive layers.
- **🔍 Typo & Fuzzy Fallback:** Automatically handles misspelled terms and queries via `difflib` vocabulary matching.
- **🌐 Multilingual & German/English Stopword Filtering:** Filters out conversational noise and matches keywords cross-lingually.
- **🔒 Race-Condition Safe:** Embedded `fcntl.flock` file locking prevents parallel `sync-turn` executions during high-frequency turns.
- **🧠 Zero External Dependencies:** Pure Python 3 standard library (`sqlite3`, `re`, `difflib`, `argparse`, `json`, `subprocess`).
- **🔌 Dual Interface:**
  - **CLI:** `prefetch`, `sync-turn`, `add`, `add-episode`, `add-learning`, `optimize`/`compact`, `list`, `--version`.
  - **MCP Server:** Standard FastMCP Model Context Protocol (`agy_memory_mcp.py`) exposing `search_memory`, `store_memory`, `record_episode`, `record_learning`, and `list_memories`.
- **⚙️ Configurable & Portable:** Database and cache paths configurable via environment variables (`AGY_MEMORY_DB`, `AGY_MEMORY_CACHE`, `AGY_BIN`).

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (standard library only, no `pip install` required)
- Google Antigravity CLI (`agy`) installed in `$PATH` or `~/.local/bin/agy` (optional, needed for automated `sync-turn`)

### 2. Manual Memory Management (CLI)
```bash
# Add Layer 1 Fact
python3 agy_memory.py add --id "user.timezone" --category "preference" --fact "Timezone is UTC+1 (CET) / UTC+2 (CEST) Zurich" --keywords "timezone zeit zeitzone zurich"

# Add Layer 2 Episode / Dossier
python3 agy_memory.py add-episode --id "project.nas_migration" --topic "infrastructure" --title "NAS Migration to TrueNAS" --narrative "Planning storage migration from OMV to TrueNAS SCALE." --keywords "nas truenas storage"

# Add Layer 3 Learning / Heuristic
python3 agy_memory.py add-learning --id "strategy.swiss_investing" --category "finance" --insight "For Swiss equity allocations, prefer CHF-hedged or local domestic funds to avoid FX drag." --keywords "finance investing chf funds"

# List stored memories across all layers
python3 agy_memory.py list

# Query / Prefetch context for an upcoming prompt
python3 agy_memory.py prefetch "Welche Server-IP hat das NAS und was ist bei CHF Anlagen zu beachten?"
```

### 3. Dynamic Conversation Turn Syncing
Pass user input and assistant response to extract and persist new facts, narrative milestones, and learnings asynchronously:
```bash
python3 agy_memory.py sync-turn --user "Remember that our staging server IP changed to 192.168.1.150" --assistant "Understood, updated the staging IP."
```

### 4. Database Optimization & Compaction (`optimize` / `compact`)

Over time, continuous background learning (`sync-turn`) can accumulate overlapping facts or fragmented notes.

```bash
# Optimize database, check keyword health, rebuild FTS5 indexes, and VACUUM SQLite
python3 agy_memory.py optimize
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
