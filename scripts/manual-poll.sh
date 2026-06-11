#!/bin/sh
# Cron poller for the "Run now" button on dworks /admin/research/prompts.
# A cheap GET checks for a pending request; only then does the agent
# container start (in --manual mode, which claims the request via POST).
# flock prevents overlapping runs — a request arriving mid-run is picked up
# by a later tick. Cron (every minute):
#   * * * * * /home/dennis/sites/research-agents/scripts/manual-poll.sh >> /home/dennis/research-agents-manual.log 2>&1
set -eu
cd "$(dirname "$0")/.."

# grep instead of sourcing: .env values aren't guaranteed shell-safe
url=$(grep -E '^DWORKS_API_URL=' .env | head -1 | cut -d= -f2-)
token=$(grep -E '^DWORKS_INGEST_TOKEN=' .env | head -1 | cut -d= -f2-)

status=$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
  -H "Authorization: Bearer $token" "$url/api/research/prompt/manual")
[ "$status" = "200" ] || exit 0

echo "[manual-poll $(date -u +%FT%TZ)] pending run detected"
exec flock -n /tmp/research-agents-manual.lock \
  docker run --rm --env-file .env \
  -v "$(pwd)/prompts:/app/prompts" \
  research-agents --manual
