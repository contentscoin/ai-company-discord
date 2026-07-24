#!/usr/bin/env bash
# Compatibility wrapper — delegates to companyctl.py (Python 3, stdlib only).
# Kept because README.md and SETUP.md reference this path. The profile list is
# now read from templates/company.discord.json, not hardcoded here. See ROADMAP.md.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 is required but was not found. Install it from https://www.python.org/" >&2
  exit 1
fi

exec "$PY" "$DIR/companyctl.py" scaffold "$@"
