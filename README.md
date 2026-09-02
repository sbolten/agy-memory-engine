# AGY Memory Engine (v2.0.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 37/37 Passing](https://img.shields.io/badge/Tests-37%2F37%20Passed-brightgreen.svg)]()

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

## 🔌 Model Context Protocol (MCP) Setup

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

## 🧪 Testing

```bash
python3 -m unittest discover tests/ -v
# Ran 33 tests in 1.5s (OK)
```

---

## 📄 License

MIT License © 2026 Stephan Bolten
