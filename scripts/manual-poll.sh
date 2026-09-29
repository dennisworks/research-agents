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
#
# Console visibility (optional): if the env file also sets AGENT_CONTROL_URL
# (+ AGENT_CONTROL_TOKEN), the run is registered with the agent-control console
# so "Run now" (queue) runs appear there alongside console-triggered runs — a
# start record before the worker runs, a finish record after. Every such call is
# best-effort (`|| true`): a console outage never blocks or fails the actual run.
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

# Hold the lock on fd 9 for the rest of the script (worker + console calls), so a
# request arriving mid-run is deferred to a later tick. Non-blocking: if a prior
# run still holds it, bail and retry next minute.
exec 9>"$LOCK"
flock -n 9 || exit 0

# Optional agent-control console registration (see header). Read from the same
# env file; absent vars just skip it and the run proceeds exactly as before.
ac_url=$(grep -E '^AGENT_CONTROL_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)
ac_token=$(grep -E '^AGENT_CONTROL_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)
ac_url=${ac_url%/}
rid=""
run_log="/tmp/research-agents-manual-$(basename "$ENV_FILE").run.log"
if [ -n "$ac_url" ]; then
  resp=$(curl -s -m 10 -H "Authorization: Bearer $ac_token" -H "Content-Type: application/json" \
    -d "{\"env_file\":\"$(basename "$ENV_FILE")\",\"input_summary\":\"Run now (prompt queue)\"}" \
    "$ac_url/runs/external" 2>/dev/null || true)
  rid=$(printf '%s' "$resp" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
  ac_log=$(printf '%s' "$resp" | sed -n 's/.*"log_path":"\([^"]*\)".*/\1/p')
  [ -n "$ac_log" ] && run_log="$ac_log"
fi

# The console-provided path must never be able to block the actual run: if it
# isn't writable, fall back to a local file (worst case /dev/null) so the worker
# always executes and the queued prompt still gets claimed.
if ! : >"$run_log" 2>/dev/null; then
  run_log="/tmp/research-agents-manual-$(basename "$ENV_FILE").run.log"
  : >"$run_log" 2>/dev/null || run_log=/dev/null
fi

# Run the worker, combined output to run_log so the console can stream it. Don't
# let a non-zero exit abort under `set -e` — record it and report instead.
code=0
docker run --rm --env-file "$ENV_FILE" \
  -v "$(pwd)/$PROMPTS_DIR:/app/prompts" \
  research-agents --manual >"$run_log" 2>&1 || code=$?

# Cron log: a one-liner on success, the full worker output on failure (keeps
# failures debuggable straight from the cron log, as before).
if [ "$code" = 0 ]; then
  echo "[manual-poll $(date -u +%FT%TZ)] run ${rid:-<unregistered>} success"
else
  echo "[manual-poll $(date -u +%FT%TZ)] run ${rid:-<unregistered>} FAILED (exit $code):"
  cat "$run_log" || true
fi

# Best-effort: finalize the console record.
if [ -n "$rid" ]; then
  st=success; [ "$code" = 0 ] || st=failed
  curl -s -m 10 -o /dev/null -H "Authorization: Bearer $ac_token" -H "Content-Type: application/json" \
    -d "{\"status\":\"$st\",\"exit_code\":$code}" \
    "$ac_url/runs/external/$rid/finish" 2>/dev/null || true
fi

exit "$code"
