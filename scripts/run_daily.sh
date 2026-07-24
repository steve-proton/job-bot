#!/usr/bin/env bash
#
# Daily entrypoint for `jobbot run`, designed to be launched by cron.
#
# cron runs with a minimal environment (bare PATH, no nvm), so this script:
#   - cd's to the repo and uses absolute paths,
#   - loads .env (for ANTHROPIC_API_KEY / overrides) if present,
#   - sources nvm so the Claude Agent SDK can find the `claude` CLI (Node),
#   - pins JOBBOT_DB to the repo, and logs each run to logs/.
#
# Env overrides: JOBBOT_LIMIT (jobs per run, default 15), JOBBOT_MODEL,
# JOBBOT_MAX_USD, JOBBOT_DB.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# Load .env if present (KEY=value lines).
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_DIR/.env"
  set +a
fi

# Make node/claude discoverable (the Agent SDK spawns the `claude` CLI).
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
# uv-managed interpreters live here.
export PATH="$HOME/.local/bin:$PATH"

export JOBBOT_DB="${JOBBOT_DB:-$REPO_DIR/jobbot.db}"

LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run-$(date +%Y%m%d-%H%M%S).log"

{
  echo "=== jobbot run start $(date -u +%FT%TZ) (db=$JOBBOT_DB, limit=${JOBBOT_LIMIT:-15}) ==="
  if "$REPO_DIR/.venv/bin/jobbot" run --limit "${JOBBOT_LIMIT:-15}"; then
    status=0
  else
    status=$?
  fi
  echo "=== jobbot run done exit=$status $(date -u +%FT%TZ) ==="
} >>"$LOG_FILE" 2>&1

# Prune logs older than 30 days so the directory doesn't grow forever.
find "$LOG_DIR" -name 'run-*.log' -type f -mtime +30 -delete 2>/dev/null || true

exit "${status:-0}"
