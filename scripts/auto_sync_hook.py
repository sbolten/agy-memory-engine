#!/usr/bin/env python3
"""
Antigravity Memory Auto-Sync Hook (Stop Lifecycle Hook)
Parses the session transcript and non-blockingly enqueues the conversation turn
into ~/.gemini/turn_queue.db, then triggers the background memory worker.
Returns in < 2ms to ensure zero latency for the user.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

# Add memory engine directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from queue_manager import enqueue_turn
except ImportError:
    enqueue_turn = None


def main():
    try:
        payload_raw = sys.stdin.read()
        if not payload_raw.strip():
            print(json.dumps({}))
            return
        payload = json.loads(payload_raw)
    except Exception:
        print(json.dumps({}))
        return

    # Always respond immediately to satisfy the Stop hook contract
    print(json.dumps({}))
    sys.stdout.flush()

    transcript_path = payload.get("transcriptPath")
    if not transcript_path or not os.path.exists(transcript_path):
        conv_id = payload.get("conversationId")
        if conv_id:
            candidate = Path.home() / ".gemini" / "antigravity-cli" / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
            if candidate.exists():
                transcript_path = str(candidate)

    if not transcript_path or not os.path.exists(transcript_path):
        return

    last_user_prompt = ""
    last_model_response = ""

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                # Look for user input
                if not last_user_prompt and data.get("type") == "USER_INPUT":
                    content = data.get("content", "")
                    if "<USER_REQUEST>" in content:
                        start = content.find("<USER_REQUEST>") + len("<USER_REQUEST>")
                        end = content.find("</USER_REQUEST>")
                        if end != -1:
                            content = content[start:end].strip()
                    last_user_prompt = content.strip()

                # Look for planner / model response text
                if not last_model_response and data.get("type") in ("PLANNER_RESPONSE", "MODEL_RESPONSE"):
                    resp = data.get("content", "")
                    if resp:
                        last_model_response = resp.strip()

                if last_user_prompt and last_model_response:
                    break
            except Exception:
                continue

    except Exception:
        return

    if not last_user_prompt:
        return

    # Guard 0: If AGY is running as part of an internal memory worker or extraction script, ignore
    if os.environ.get("AGY_INTERNAL_INVOCATION") == "1":
        return

    # Guard 1: Filter internal prompts and automated background jobs
    internal_markers = [
        "Multi-Layer Cognitive Memory Engine",
        "Du bist Stephans persönlicher autonomer KI-Assistent in Zürich für das Paket",
        "PROFIL Stephan:",
        "TPA BOT REPORT",
        "STATUS-SNAPSHOT [Paket:",
        "AGY Bot Integrity Watchdog"
    ]
    if any(m in last_user_prompt for m in internal_markers):
        return

    # 1. Enqueue turn in local SQLite queue (< 1ms)
    if enqueue_turn:
        enqueue_turn(
            user_prompt=last_user_prompt[:4000],
            assistant_response=last_model_response[:4000] if last_model_response else "Action executed successfully.",
            source="hook",
            chat_id="299090858"
        )


if __name__ == "__main__":
    main()
