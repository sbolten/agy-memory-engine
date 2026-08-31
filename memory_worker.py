#!/usr/bin/env python3
"""
Autonomous Asynchronous Memory Worker for Antigravity (AGY).
Processes dialogue turns from ~/.gemini/turn_queue.db in the background,
extracts facts/episodes/learnings into ~/.gemini/memory.db,
and sends a brief informative notification to Telegram whenever new knowledge is stored.
"""

import os
import sys
import fcntl
import tempfile
import argparse
import subprocess
from pathlib import Path

# Add memory engine directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from queue_manager import (
    get_pending_turns,
    mark_turn_status,
    prune_processed_turns,
    QUEUE_DB_PATH
)
from agy_memory import is_trivial_prompt, sync_turn

LOCK_FILE = Path.home() / ".gemini" / "memory_worker.lock"
SEND_TELEGRAM_BIN = Path.home() / "bin" / "send_telegram.py"
DEFAULT_TELEGRAM_CHAT_ID = "299090858"


def send_telegram_notification(message: str, chat_id: str = None) -> bool:
    """Send an informative notification to Telegram via send_telegram.py."""
    target_chat = chat_id or DEFAULT_TELEGRAM_CHAT_ID
    if SEND_TELEGRAM_BIN.exists():
        try:
            res = subprocess.run(
                ["python3", str(SEND_TELEGRAM_BIN), "--chat-id", str(target_chat), message],
                capture_output=True, text=True, timeout=15
            )
            return res.returncode == 0
        except Exception as e:
            sys.stderr.write(f"Failed to send telegram notification: {e}\n")
            return False
    return False


def format_notification(changes: dict) -> str:
    """Format extracted memory changes into a concise Telegram notification."""
    lines = ["🧠 *[Autonomes Gedächtnis aktualisiert]*\n"]
    
    # Facts
    facts = changes.get("facts", [])
    for f in facts:
        action = "Aktualisierter Fakt" if f.get("is_update") else "Neuer Fakt"
        fact_text = f.get("fact", "")
        short_fact = (fact_text[:80] + "...") if len(fact_text) > 80 else fact_text
        lines.append(f"• *{action}:* `{f.get('id')}`\n  _{short_fact}_")

    # Episodes
    episodes = changes.get("episodes", [])
    for ep in episodes:
        action = "Episode aktualisiert" if ep.get("is_update") else "Neue Episode"
        lines.append(f"• *{action}:* `{ep.get('id')}` ({ep.get('title', '')})")

    # Learnings
    learnings = changes.get("learnings", [])
    for lr in learnings:
        action = "Learning aktualisiert" if lr.get("is_update") else "Neues Learning"
        insight_text = lr.get("insight", "")
        short_insight = (insight_text[:80] + "...") if len(insight_text) > 80 else insight_text
        lines.append(f"• *{action}:* `{lr.get('id')}`\n  _{short_insight}_")

    # Entity Links
    links = changes.get("entity_links", [])
    for el in links:
        lines.append(f"• *Entity-Link:* `{el.get('source')}` ➔ `[{el.get('relation')}]` ➔ `{el.get('target')}`")

    lines.append("\n_Automatisch im Hintergrund gelernt und in memory.db gesichert._")
    return "\n".join(lines)


def process_queue(batch_size: int = 10, notify: bool = True) -> int:
    """Process pending turns in batch."""
    pending = get_pending_turns(limit=batch_size)
    if not pending:
        return 0

    processed_count = 0
    
    # Group turns by chat_id/source if needed, or process in sequence
    for turn in pending:
        turn_id = turn["id"]
        chat_id = turn["chat_id"] or DEFAULT_TELEGRAM_CHAT_ID
        user_prompt = turn["user_prompt"]
        assistant_resp = turn["assistant_response"]

        # Fast filter for trivial turns (e.g. 'ok', 'ja', 'danke')
        if is_trivial_prompt(user_prompt):
            mark_turn_status([turn_id], status="skipped", summary="Trivial prompt skipped")
            processed_count += 1
            continue

        try:
            # Run sync-turn extraction
            changes = sync_turn(user_prompt, assistant_resp, dry_run=False)
            
            has_changes = any(bool(changes.get(k)) for k in ["facts", "episodes", "learnings", "entity_links"])
            
            summary_parts = []
            if changes.get("facts"): summary_parts.append(f"{len(changes['facts'])} facts")
            if changes.get("episodes"): summary_parts.append(f"{len(changes['episodes'])} episodes")
            if changes.get("learnings"): summary_parts.append(f"{len(changes['learnings'])} learnings")
            if changes.get("entity_links"): summary_parts.append(f"{len(changes['entity_links'])} links")
            
            summary = ", ".join(summary_parts) if summary_parts else "No persistent entities found"
            mark_turn_status([turn_id], status="processed", summary=summary)

            # Send Telegram notification ONLY if new or updated knowledge was discovered
            if has_changes and notify:
                msg = format_notification(changes)
                send_telegram_notification(msg, chat_id=chat_id)

            processed_count += 1
        except Exception as e:
            sys.stderr.write(f"Error processing turn {turn_id}: {e}\n")
            mark_turn_status([turn_id], status="failed", error=str(e))

    # Clean up old processed items
    prune_processed_turns(days=7)
    return processed_count


def main():
    parser = argparse.ArgumentParser(description="Autonomous AGY Memory Queue Worker")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of turns to process per run")
    parser.add_argument("--no-notify", action="store_true", help="Disable Telegram notification")
    parser.add_argument("--async", dest="async_mode", action="store_true", help="Run in non-blocking daemon mode")
    args = parser.parse_args()

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Worker is already running — exit cleanly without waiting
        sys.exit(0)

    try:
        count = process_queue(batch_size=args.batch_size, notify=not args.no_notify)
        if count > 0:
            print(f"Memory Worker: Processed {count} turn(s).")
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
