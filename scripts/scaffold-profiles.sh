#!/usr/bin/env bash
# Scaffold Hermes profiles for Discord-first AI Company.
# Does NOT write secrets. Safe to re-run (skips existing files).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PROFILES_DIR="$HERMES_HOME/profiles"
PROFILES=(ceo cto loop growth critic)

echo "==> Hermes home: $HERMES_HOME"
mkdir -p "$PROFILES_DIR"

for name in "${PROFILES[@]}"; do
  dest="$PROFILES_DIR/$name"
  mkdir -p "$dest" "$dest/skills" "$dest/memories"
  echo "-- profile: $name"

  if [[ ! -f "$dest/SOUL.md" ]]; then
    cp "$ROOT/profiles/$name/SOUL.md" "$dest/SOUL.md"
    echo "   wrote SOUL.md"
  else
    echo "   keep existing SOUL.md"
  fi

  if [[ ! -f "$dest/config.yaml" ]]; then
    cp "$ROOT/templates/config.yaml" "$dest/config.yaml"
    # CEO gets a commented standup hint
    if [[ "$name" == "ceo" ]]; then
      cat >> "$dest/config.yaml" <<'EOF'

# Uncomment and set #standup channel snowflake to allow cron posts without mention:
# discord:
#   free_response_channels: "STANDUP_CHANNEL_ID"
EOF
    fi
    echo "   wrote config.yaml"
  else
    echo "   keep existing config.yaml"
  fi

  if [[ ! -f "$dest/.env" ]]; then
    cp "$ROOT/templates/env.example" "$dest/.env"
    echo "   wrote .env (fill DISCORD_BOT_TOKEN)"
  else
    echo "   keep existing .env"
  fi
done

echo
echo "Next:"
echo "  1) Create 5 Discord apps/bots and paste tokens into each .env"
echo "  2) Invite bots to your server (see SETUP.md)"
echo "  3) hermes -p ceo gateway start   # repeat for each profile"
echo "  4) Smoke-test @mentions in #exec-meeting"
