#!/usr/bin/env python3
"""
Antigravity Memory Auto-Sync Hook (Stop Lifecycle Hook)
Parses the session transcript and automatically triggers agy_memory.py sync-turn
in a detached background process to prevent blocking the agent termination.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

def main():
    try:
        payload_raw = sys.stdin.read()
        if not payload_raw.strip():
            print(json.dumps({"decision": "allow"}))
            return
        payload = json.loads(payload_raw)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    # Always respond immediately to satisfy the Stop hook contract
    # Stop hook contract: {"decision": "allow"} or {"decision": "continue", "reason": "..."}
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

    sync_script = "/home/ubuntu/dev/agy-memory-engine/agy_memory.py"
    if not os.path.exists(sync_script):
        sync_script = "/opt/agy-memory-engine/agy_memory.py"

    cmd = [
        "python3",
        sync_script,
        "sync-turn",
        "--user",
        last_user_prompt[:4000],
        "--assistant",
        last_model_response[:4000] if last_model_response else "Action executed successfully."
    ]

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception:
        pass

if __name__ == "__main__":
    main()
