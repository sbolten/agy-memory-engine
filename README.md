# agy-memory-engine

> Standalone Dynamic Memory Layer for Google Antigravity (`agy`) and Telegram Gateway.

Inspired by Hermes Agent's 3-pillar memory architecture, using SQLite FTS5 for fast local search and `agy` subagents (`flash_lite`) for asynchronous background extraction & upserting.

## Architecture

- **SQLite FTS5 DB**: Stored locally at `~/.gemini/memory.db`.
- **CLI (`agy_memory.py`)**: Prefetch (<2ms FTS5 search with trivial prompt filtering), async `sync-turn`, manual CRUD.
- **MCP Server (`agy_memory_mcp.py`)**: Exposes `search_memory`, `store_memory`, and `list_memories` tools to `agy`.

## CLI Usage

```bash
# Prefetch context for a prompt
python3 agy_memory.py prefetch "Wie erreiche ich den Beelink?"

# Asynchronously sync a turn
python3 agy_memory.py sync-turn --user "User prompt" --assistant "Assistant response"

# Manual memory management
python3 agy_memory.py add --id "device.ip" --category "hardware" --fact "IP 100.114.118.47"
python3 agy_memory.py list
```
