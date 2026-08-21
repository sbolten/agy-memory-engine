#!/bin/bash
# ==============================================================================
# AGY Memory Engine - Multi-User Nightly Compact & Deduplication
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="${AGY_MEMORY_PY:-$SCRIPT_DIR/agy_memory.py}"

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Memory engine script not found at $SCRIPT_PATH" >&2
    exit 1
fi

for udir in /home/*; do
    [ -d "$udir" ] || continue
    username=$(basename "$udir")
    db="$udir/.gemini/memory.db"
    
    if [ -f "$db" ] && id "$username" >/dev/null 2>&1; then
        # Run compaction as the respective user to maintain proper file permissions
        su - "$username" -c "/usr/bin/python3 \"$SCRIPT_PATH\" compact --apply >/dev/null 2>&1" || true
    fi
done
