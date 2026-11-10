#!/usr/bin/env bash
# Run the daily sync. usage: bash tools/run_sync.sh [--dry-run]   (from a checkout of the mirror-state branch)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
URL="${MIRROR_URL:-https://github.com/ThePharmer/nest-hub-fuchsia-mirror.git}"
python3 -I -B "$HERE/sync.py" --url "$URL" --work "${SYNC_WORK:-$HERE/../../sync-work}" "$@"
