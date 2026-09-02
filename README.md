# AGY Memory Engine (v2.0.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 41/41 Passing](https://img.shields.io/badge/Tests-41%2F41%20Passed-brightgreen.svg)]()

> Lightweight, high-performance, standalone dynamic cognitive memory layer for Google Antigravity (`agy`) and autonomous agent frameworks.

Inspired by Hermes Agent's multi-pillar memory architecture, using SQLite FTS5 for ultra-fast local retrieval (<2ms), multilingual compound sub-token decomposition & morphological stemming (DE, EN, FR, IT, ES, NL, SV), relational entity linking, and autonomous background queue workers with calm-memory session debouncing.

---

## 🧩 The Big Picture: Autonomous Omni-Channel Stack

`agy-memory-engine` acts as the persistent semantic backbone across all client interfaces (Telegram, Terminal CLI, Web Cockpit, IDE):

```text
                  ┌────────────────────────────────────────────────────────┐
                  │    Omni-Channel Interfaces (Telegram, CLI, Web, IDE)   │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                    ┌────────────────────────────────────────────────────┐
                    │       Global AGY Stop-Hook (hooks.json)            │
                    │   • Enqueues turn in < 1ms to turn_queue.db        │
                    │   • Zero latency impact on active conversations    │
                    └─────────────────────────┬──────────────────────────┘
                                              │
                                              ▼ (5m Idle OR 15m Timeout)
                    ┌────────────────────────────────────────────────────┐
                    │      Calm Memory Worker (memory_worker.py)         │
                    │   • Batches full conversation into 1 LLM pass      │
                    │   • Single consolidated Telegram status update     │
                    │   • Loop prevention (AGY_INTERNAL_INVOCATION=1)    │
                    └─────────────────────────┬──────────────────────────┘
                                              │
                                              ▼
                    ┌────────────────────────────────────────────────────┐
                    │     4-Layer Cognitive Memory (~/.gemini/memory.db) │
                    │   • Layer 1: Atomic Facts (memories)               │
                    │   • Layer 2: Narrative Episodes (episodes)         │
                    │   • Layer 3: Experiential Learnings (learnings)    │
                    │   • Layer 4: Relational Entity Graph (links)       │
                    └────────────────────────────────────────────────────┘
```

---

## 🏛️ The 4-Layer Cognitive Memory Model

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ~/.gemini/memory.db                                      │
├───────────────────┬────────────────────────────┬────────────────────────────┬───────────────┤
│ Layer 1: Facts    │ Layer 2: Narrative Dossiers│ Layer 3: Learnings         │ Layer 4: Graph│
│   (`memories`)    │        (`episodes`)        │       (`learnings`)        │(`entity_links`)
├───────────────────┼────────────────────────────┼────────────────────────────┼───────────────┤
│ - Server IPs/ports│ - Background histories     │ - Rules of thumb, lessons  │ - Directional │
│ - Hardware specs  │ - Stances & sentiment      │ - Tested heuristics        │   relations   │
│ - Master data     │ - Lifecycle status decay   │ - Contextual guidelines    │   (hosted_on, │
│ - Exact BM25 match│   (active->cooling->past)  │ - Decision rationale       │    owns, etc.)│
└───────────────────┴────────────────────────────┴────────────────────────────┴───────────────┘
```

---

## 🔍 Hybrid Multilingual Tokenizer vs. Vector Databases

Rather than requiring heavyweight PyTorch / ONNX vector libraries (~500MB RAM, 150ms latency), `agy-memory-engine` implements an in-process **Hybrid Multilingual Semantic Tokenizer**:

1. **Multilingual Compound Sub-Token Decomposition:** Automatically decomposes composite nouns across German, Dutch, Scandinavian and Romance languages (e.g. `Hundeversicherung` ➔ `hund` + `versicherung`, `Zweitwohnungssteuer` ➔ `zweitwohnung` + `steuer`, `hondenverzekering` ➔ `hond` + `verzekering`) with Fugenmorpheme handling (`-s-`, `-en-`, `-n-`, `-er-`, `-e-`) and database vocabulary validation.
2. **Morphological Suffix & Stemming Normalizer:** Normalizes inflectional endings across 8 European languages (DE, EN, FR, IT, ES, NL, SV/NO/DA) so inflected queries (e.g. `insurances`, `voitures`, `prenotazioni`, `reservaciones`) match stored canonical records.
3. **BM25 Relevance Scoring:** Fast native SQLite FTS5 rank over facts, episodes, and learnings.
4. **Status-Aware Aging:** Weights `active` topics above `cooling` and `historic` dossiers.
5. **1-Hop Entity Expansion:** Resolves linked hardware/services automatically during prefetch.
6. **Exact Match Guarantee:** 100% precision on IP addresses, ports, IDs, and serial numbers.

---

## 🚀 CLI Quick Start

```bash
# Multi-Layer Prefetch (< 2ms)
python3 agy_memory.py prefetch "Hundeversicherung"

# Add Layer 1 Fact
python3 agy_memory.py add --id "infra.beelink.ip" --category "infra" --fact "Beelink Host IP is 100.114.118.47" --keywords "beelink host server ip"

# Add Layer 2 Episode
python3 agy_memory.py add-episode --id "travel.iceland2027" --topic "travel" --title "Laugavegur Trekking" --narrative "Hut booking watchdog active for July 2027." --status "active" --keywords "island laugavegur"

# Add Layer 3 Learning
python3 agy_memory.py add-learning --id "travel.flights.cdp" --category "travel" --insight "Use CDP browser for Google Flights to avoid bot-blocking." --keywords "google flights bot cdp"

# Link Entities in Graph
python3 agy_memory.py link --source "service.immich" --target "infra.beelink.ip" --relation "hosted_on"

# Optimize & Decay Maintenance
python3 agy_memory.py optimize --apply
```

---

## 🔌 Model Context Protocol (MCP) Server

The engine includes a native FastMCP server (`agy_memory_mcp.py`) that equips autonomous AI agents (Antigravity, Claude, Cursor, OpenCode) with explicit memory reading and writing capabilities:

### Available MCP Tools

| Tool | Description | Key Parameters |
| :--- | :--- | :--- |
| `search_memory` | Hybrid multilingual search across Facts, Episodes, Learnings & Graph relations | `query` *(str)*, `limit` *(int, default: 5)* |
| `store_memory` | Store or update an atomic configuration parameter or fact (Layer 1) | `id`, `fact`, `category`, `keywords` |
| `record_episode` | Record a rich narrative chronicle, ongoing topic, or history (Layer 2) | `id`, `topic`, `title`, `narrative`, `status`, `stance` |
| `record_learning` | Record a practical heuristic, tested rule of thumb, or stance (Layer 3) | `id`, `category`, `insight`, `context`, `keywords` |
| `link_entities_mcp` | Create directional knowledge graph links between memory entities (Layer 4) | `source_id`, `target_id`, `relation` |
| `list_memories` | Full multi-layer inventory export of all stored memories | — |

### MCP Configuration

Add to your MCP settings file (e.g. `~/.gemini/antigravity-cli/mcp_config.json` or Claude/Cursor config):

```json
{
  "mcpServers": {
    "memory": {
      "command": "python3",
      "args": ["/opt/agy-memory-engine/agy_memory_mcp.py"],
      "env": {
        "AGY_MEMORY_DB": "~/.gemini/memory.db"
      }
    }
  }
}
```

---

## 📱 Seamless Integration with Antigravity Telegram Bot

`agy-memory-engine` is designed to work in synergy with the [Antigravity Telegram Bot (`antigravity-cli-telegram-bot`)](https://github.com/sbolten/antigravity-cli-telegram-bot) to form a completely autonomous, mobile memory pipeline:

```text
  📱 Mobile User in Telegram (Voice, Text, Photos, Topics)
            │
            ▼
  🤖 AGY Telegram Bot (/opt/agy-telegram-bot)
            │  (Executes standard agy prompt with --add-dir)
            ▼
  ⚡ AGY Global Stop-Hook (~/.gemini/config/hooks.json -> scripts/auto_sync_hook.py)
            │  (Enqueues turn in <1ms to turn_queue.db, resolves Telegram topic/chat ID)
            ▼
  🧠 Calm Memory Worker (memory_worker.py)
            │  (Debounces 5m idle / 15m timeout, batches conversation into 1 LLM pass)
            ▼
  💾 SQLite FTS5 Memory Store (~/.gemini/memory.db)
            │
            ▼
  📲 Instant Status Notification back to Telegram Topic / Chat
     "🧠 Autonomes Gedächtnis aktualisiert (1 Fakt, 1 Learning)
      • ➕ Beelink Host IP is 100.114.118.47
      • ➕ Use CDP browser for Google Flights"
```

### Key Synergy Highlights:
1. **Zero Chat Latency:** The global stop-hook returns in `< 1ms`, ensuring the Telegram Bot responds instantly without waiting for memory extraction.
2. **Context-Aware Topic Routing:** The worker automatically preserves the originating Telegram `chat_id` and `message_thread_id`, routing notifications directly back into the relevant topic thread.
3. **Loop Prevention:** Ingestion runs under `AGY_INTERNAL_INVOCATION=1` with prompt marker guards to prevent recursive agent loops.

---

## ⚙️ Configuration (`.env`)

All engine parameters, database locations, LLM model choice, and debounce thresholds can be configured via `.env` (or environment variables). A ready-to-use template is provided in [`.env.example`](file:///opt/agy-memory-engine/.env.example):

```bash
# Copy template to .env
cp .env.example .env
```

```ini
# ==============================================================================
# AGY Memory Engine - Configuration File
# ==============================================================================

# LLM model used for background memory extraction & consolidation
AGY_MEMORY_MODEL=gemini-3.7-flash-high

# SQLite Database Storage Paths
AGY_MEMORY_DB=~/.gemini/memory.db
AGY_TURN_QUEUE_DB=~/.gemini/turn_queue.db

# Calm-Memory Debounce Settings (in seconds)
AGY_MEMORY_INACTIVITY_SECONDS=300   # 5 minutes idle threshold
AGY_MEMORY_MAX_WAIT_SECONDS=900     # 15 minutes max timeout

# Telegram Notification Recipient
AGY_MEMORY_TELEGRAM_CHAT_ID=299090858

# Path to Antigravity CLI binary
AGY_BIN=agy

# Real-Time Debug Dashboard (Web UI)
AGY_MEMORY_DEBUG_DASHBOARD=true
AGY_MEMORY_DASHBOARD_PORT=8085
AGY_MEMORY_DASHBOARD_HOST=0.0.0.0
```

---

## 📊 Real-Time Debug Web Dashboard

A zero-dependency, standalone live web dashboard is included to inspect, search, and monitor memory state in real time:

* **Live FTS5 Search Sandbox:** Test hybrid multilingual queries with sub-millisecond latency metrics.
* **Turn Queue & Debounce Monitor:** Visual countdown bar for active conversation debouncing (5m idle / 15m timeout) with an instant *"Batch jetzt verarbeiten"* trigger.
* **4-Layer Visualizer:** Browse Facts (Layer 1), Thematic Episodes with status badges (Layer 2), Experiential Learnings (Layer 3), and Knowledge Graph Entity Links (Layer 4).
* **Consolidation Audit Log:** Review automated background merges, deduplications, and semantic rationale.

### Starting the Dashboard

```bash
# Via CLI command
python3 agy_memory.py ui --port 8085

# Or directly via standalone runner
python3 dashboard.py --port 8085

# Or via systemd background user service
systemctl --user start agy-memory-dashboard.service
```

Access in your browser at `http://localhost:8085` (or over Tailscale at `http://<tailscale-ip>:8085`).

---

## ⏰ Autonomous Background Pipeline (Cron & Lifecycle Hooks)

To enable 100% autonomous background learning without manual intervention, configure the **AGY Lifecycle Hook** and the **Linux Crontab**:

### 1. Global Lifecycle Hook (`~/.gemini/config/hooks.json`)

Registers the sub-millisecond transcript collector on every agent turn stop:

```json
{
  "memory-auto-sync": {
    "enabled": true,
    "Stop": [
      {
        "type": "command",
        "command": "python3 /opt/agy-memory-engine/scripts/auto_sync_hook.py",
        "timeout": 15
      }
    ]
  }
}
```

### 2. Crontab Configuration (`crontab -e`)

```bash
# Process pending memory queue every 5 minutes (debounced)
*/5 * * * * python3 /opt/agy-memory-engine/memory_worker.py >/dev/null 2>&1

# Nightly memory decay aging, duplicate consolidation & VACUUM (04:30)
30 4 * * * python3 /opt/agy-memory-engine/agy_memory.py optimize --apply >/dev/null 2>&1
```

---

## 🧪 Testing

```bash
python3 -m unittest discover tests/ -v
# Ran 41 tests in 1.5s (OK)
```

---

## 📄 License

MIT License © 2026 Stephan Bolten
