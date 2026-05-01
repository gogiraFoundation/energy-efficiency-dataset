#!/usr/bin/env bash
set -euo pipefail

# Run the Streamlit dashboard from repo root (required for package imports).
# Usage:
#   ./scripts/run_dashboard.sh
#   ./scripts/run_dashboard.sh --server.port 8502
#
# Set DATABASE_URL in .env at the repo root, or export it before running.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

exec python3 -m streamlit run dashboard/app.py "$@"
