#!/usr/bin/env bash
# Create contentscoin/ai-company-discord (public) and push this directory.
# Run on a machine where `gh` can create repos (personal PAT / owner account).
# Cloud agent tokens are usually read-only and cannot run this.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="${GITHUB_OWNER:-contentscoin}"
REPO_NAME="${REPO_NAME:-ai-company-discord}"
FULL="$OWNER/$REPO_NAME"

cd "$ROOT"

if [[ ! -d .git ]]; then
  git init -b main
  git add .
  git commit -m "Initial commit: Discord-first AI Company OS"
fi

if gh repo view "$FULL" >/dev/null 2>&1; then
  echo "Repo $FULL already exists — setting remote and pushing"
else
  echo "Creating public repo $FULL"
  gh repo create "$FULL" --public --source=. --remote=origin --push \
    --description "Discord-first AI Company OS: Hermes souls, GJC roles, Paperclip + OpenCrab"
  echo "Done: https://github.com/$FULL"
  exit 0
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$FULL.git"
git push -u origin HEAD:main
echo "Pushed: https://github.com/$FULL"
