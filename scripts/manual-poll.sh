#!/bin/sh
# Optional: cron poller for an on-demand "Run now" request from a publish
# backend (see remote_prompts.claim_manual). A cheap GET checks for a pending
# request; only then does the agent container start in --manual mode, which
# claims the request via POST. flock prevents overlapping runs — a request
# arriving mid-run is picked up by a later tick.
#
# Multi-backend: pass an env file and prompts dir to target a second backend.
# A no-arg call keeps the original single-backend operation — same .env,
# prompts/, endpoints, and claim flow; the only differences from the previous
# script are that the lock filename and the "pending run" log line now carry the
# env-file name, so two backends can poll concurrently without sharing a lock.
# Cron:
#   * * * * * /path/to/scripts/manual-poll.sh >> /path/to/manual.log 2>&1
#   * * * * * /path/to/scripts/manual-poll.sh .env.other prompts-other >> ... 2>&1
#
# Only useful alongside a backend that implements the prompt-queue endpoints;
# a file-only setup doesn't need this.
set -eu
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
PROMPTS_DIR="${2:-prompts}"
LOCK="/tmp/research-agents-manual-$(basename "$ENV_FILE").lock"

# grep instead of sourcing: .env values aren't guaranteed shell-safe. Values
# must be unquoted (the `docker --env-file` convention this repo already
# follows) — `cut` keeps everything after the first '=' verbatim.
# PUBLISH_* are the current names; DWORKS_* are honored for older configs.
url=$(grep -E '^(PUBLISH_URL|DWORKS_API_URL)=' "$ENV_FILE" | head -1 | cut -d= -f2-)
token=$(grep -E '^(PUBLISH_TOKEN|DWORKS_INGEST_TOKEN)=' "$ENV_FILE" | head -1 | cut -d= -f2-)
url=${url%/}   # strip a trailing slash so "$url/api/..." can't 308 on a double //

# `|| true`: a curl connect/timeout failure must not abort the poll under
# `set -e` — treat it as "no pending run" and try again next minute.
status=$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
  -H "Authorization: Bearer $token" "$url/api/research/prompt/manual" || true)
[ "$status" = "200" ] || exit 0

echo "[manual-poll $(date -u +%FT%TZ)] pending run detected ($ENV_FILE)"
exec flock -n "$LOCK" \
  docker run --rm --env-file "$ENV_FILE" \
  -v "$(pwd)/$PROMPTS_DIR:/app/prompts" \
  research-agents --manual
