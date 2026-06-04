#!/usr/bin/env bash
# Wrapper invoked by launchd (or cron on Linux). Runs the digest using the
# project-local venv so the scheduler doesn't depend on the user's shell env.
#
# Credentials and feature flags are read from the environment here and forwarded
# as CLI args. Set them in the launchd plist / cron env, or `source` a creds
# file before this script:
#   DEEPSEEK_API_KEY=...
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHAT_ID=...          # may be comma-separated for fan-out
#   TELEGRAM_SEND=true            # or false to dry-run
#   MIN_UPVOTES=5
#   ATTACH_PDF=false
#   MODE=digest                   # digest (default) or recap
#   RECAP_DAYS=7
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"

: "${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY must be set}"
: "${TELEGRAM_SEND:=true}"
: "${MIN_UPVOTES:=5}"
: "${ATTACH_PDF:=false}"
: "${MODE:=digest}"
: "${RECAP_DAYS:=7}"

ARGS=(
  --deepseek-api-key "$DEEPSEEK_API_KEY"
  --telegram-send "$TELEGRAM_SEND"
  --min-upvotes "$MIN_UPVOTES"
  --attach-pdf "$ATTACH_PDF"
  --mode "$MODE"
  --recap-days "$RECAP_DAYS"
)

if [[ "$TELEGRAM_SEND" == "true" ]]; then
  : "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN must be set when TELEGRAM_SEND=true}"
  : "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID must be set when TELEGRAM_SEND=true}"
  ARGS+=(--telegram-bot-token "$TELEGRAM_BOT_TOKEN" --telegram-chat-id "$TELEGRAM_CHAT_ID")
fi

exec python -m src.main "${ARGS[@]}"
