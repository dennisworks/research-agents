#!/bin/sh
# Optional: cron poller for an on-demand "Run now" request from a publish
# backend (see remote_prompts.claim_manual). A cheap GET checks for a pending
# request; only then does the agent container start in --manual mode, which
# claims the request via POST. flock prevents overlapping runs — a request
# arriving mid-run is picked up by a later tick. Cron (every minute):
#   * * * * * /path/to/research-agents/scripts/manual-poll.sh >> /path/to/manual.log 2>&1
#
# Only useful alongside a backend that implements the prompt-queue endpoints;
# a file-only setup doesn't need this.
set -eu
cd "$(dirname "$0")/.."

# grep instead of sourcing: .env values aren't guaranteed shell-safe.
# PUBLISH_* are the current names; DWORKS_* are honored for older configs.
url=$(grep -E '^(PUBLISH_URL|DWORKS_API_URL)=' .env | head -1 | cut -d= -f2-)
token=$(grep -E '^(PUBLISH_TOKEN|DWORKS_INGEST_TOKEN)=' .env | head -1 | cut -d= -f2-)

status=$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
  -H "Authorization: Bearer $token" "$url/api/research/prompt/manual")
[ "$status" = "200" ] || exit 0

echo "[manual-poll $(date -u +%FT%TZ)] pending run detected"
exec flock -n /tmp/research-agents-manual.lock \
  docker run --rm --env-file .env \
  -v "$(pwd)/prompts:/app/prompts" \
  research-agents --manual
