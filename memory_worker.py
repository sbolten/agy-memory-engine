#!/usr/bin/env python3
"""
Autonomous Calm Memory Worker for Antigravity (AGY).
Processes conversation batches from ~/.gemini/turn_queue.db only when:
1. The last message is at least 5 minutes old (inactivity debounce), OR
2. The oldest pending message has waited for 30 minutes (max timeout), OR
3. Explicitly forced via --force (e.g. /remember command).
"""

import os
import sys
import fcntl
import argparse
import subprocess
from pathlib import Path

# Add memory engine directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from queue_manager import (
    get_pending_stats,
    get_pending_turns,
    mark_turn_status,
    prune_processed_turns,
    QUEUE_DB_PATH
)
from agy_memory import is_trivial_prompt, sync_turn

LOCK_FILE = Path.home() / ".gemini" / "memory_worker.lock"
SEND_TELEGRAM_BIN = Path.home() / "bin" / "send_telegram.py"
DEFAULT_TELEGRAM_CHAT_ID = "299090858"

INACTIVITY_THRESHOLD_SECONDS = 300   # 5 minutes idle
MAX_WAIT_THRESHOLD_SECONDS = 900     # 15 minutes max wait


def send_telegram_notification(message: str, chat_id: str = None) -> bool:
    """Send an informative notification to Telegram via send_telegram.py."""
    if SEND_TELEGRAM_BIN.exists():
        try:
            cmd = ["python3", str(SEND_TELEGRAM_BIN)]
            if chat_id:
                cmd.extend(["--chat-id", str(chat_id)])
            cmd.append(message)
            res = subprocess.run(
                cmd,
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


def should_process_queue(force: bool = False) -> tuple[bool, str]:
    """Check if the calm-memory threshold conditions are satisfied."""
    if force:
        return True, "Forced run"

    stats = get_pending_stats()
    count = stats["count"]
    if count == 0:
        return False, "Queue is empty"

    newest_age = stats["newest_age_seconds"]
    oldest_age = stats["oldest_age_seconds"]

    # Condition 1: Inactivity debounce (5 min of silence)
    if newest_age >= INACTIVITY_THRESHOLD_SECONDS:
        return True, f"Inactivity threshold met (idle for {newest_age}s, {count} turns)"

    # Condition 2: Max wait time (30 min timeout)
    if oldest_age >= MAX_WAIT_THRESHOLD_SECONDS:
        return True, f"Max wait threshold met (oldest turn {oldest_age}s, {count} turns)"

    return False, f"Chat actively in progress (last message {newest_age}s ago, waiting for 5m idle)"


def process_queue(batch_size: int = 25, notify: bool = True) -> int:
    """Process pending conversation turns in a unified, contextual batch."""
    pending = get_pending_turns(limit=batch_size)
    if not pending:
        return 0

    turn_ids = [t["id"] for t in pending]
    notification_chat_id = pending[-1]["chat_id"] if pending[-1].get("chat_id") else None

    dialogue_blocks = []
    for turn in pending:
        u = turn["user_prompt"].strip()
        a = turn["assistant_response"].strip()
        if is_trivial_prompt(u):
            continue
        dialogue_blocks.append(f"User: {u}\nAssistant: {a}")

    if not dialogue_blocks:
        mark_turn_status(turn_ids, status="skipped", summary="All turns trivial")
        prune_processed_turns(days=7)
        return len(turn_ids)

    combined_dialogue = "\n\n---\n\n".join(dialogue_blocks)

    try:
        changes = sync_turn(
            user_prompt=combined_dialogue,
            assistant_response="Conversation batch complete.",
            dry_run=False
        )

        has_changes = any(bool(changes.get(k)) for k in ["facts", "episodes", "learnings", "entity_links"])
        summary_parts = []
        if changes.get("facts"): summary_parts.append(f"{len(changes['facts'])} facts")
        if changes.get("episodes"): summary_parts.append(f"{len(changes['episodes'])} episodes")
        if changes.get("learnings"): summary_parts.append(f"{len(changes['learnings'])} learnings")
        if changes.get("entity_links"): summary_parts.append(f"{len(changes['entity_links'])} links")

        summary = ", ".join(summary_parts) if summary_parts else "No persistent entities found"
        mark_turn_status(turn_ids, status="processed", summary=summary)

        if has_changes and notify:
            msg = format_notification(changes)
            send_telegram_notification(msg, chat_id=notification_chat_id)

    except Exception as e:
        sys.stderr.write(f"Error during batch sync: {e}\n")
        mark_turn_status(turn_ids, status="failed", error=str(e))

    prune_processed_turns(days=7)
    return len(turn_ids)


def main():
    parser = argparse.ArgumentParser(description="Autonomous Calm AGY Memory Queue Worker")
    parser.add_argument("--batch-size", type=int, default=25, help="Number of turns to process per run")
    parser.add_argument("--force", action="store_true", help="Force processing regardless of 5m idle or 30m timer")
    parser.add_argument("--no-notify", action="store_true", help="Disable Telegram notification")
    args = parser.parse_args()

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)

    try:
        can_run, reason = should_process_queue(force=args.force)
        if not can_run:
            sys.exit(0)

        count = process_queue(batch_size=args.batch_size, notify=not args.no_notify)
        if count > 0:
            print(f"Memory Worker: Processed batch of {count} turn(s) ({reason}).")
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
