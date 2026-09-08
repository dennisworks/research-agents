# DRAFT — adding mumblingpundit as a second publish backend (VPS cron)

The daily research run is a **plain OS crontab** for user `dennis` on the VPS
(`crontab -e`), not an OpenClaw job. OpenClaw only owns `linkedin-import`.
mumblingpundit reuses the *same image* and repo; it's a second env file + a
second crontab pair. Nothing here is applied yet — apply on the VPS when
mumblingpundit's `/api/research/*` endpoints are live.

Fill in before applying:
- `<MP_PUBLISH_URL>` — mumblingpundit's production URL (Vercel domain).
- `<MP_CRON_SECRET>` — must equal mumblingpundit's `CRON_SECRET` env var.

## 1. Env file — `/home/dennis/sites/research-agents/.env.mumblingpundit`
Reuses the shared Anthropic/Tavily keys; only the backend + token differ.
```
ANTHROPIC_API_KEY=<same value as .env>
TAVILY_API_KEY=<same value as .env>
PROMPT_TZ=UTC
PUBLISH_URL=<MP_PUBLISH_URL>
PUBLISH_TOKEN=<MP_CRON_SECRET>
```

## 2. Dedicated prompts fallback — `prompts-mumblingpundit/`
mumblingpundit's briefs live in its **own DB queue** (served by
`/api/research/prompt`), which resolves first. The mounted `prompts/` dir is only
a fallback for when the queue is empty. Do **not** mount the shared `prompts/` —
its `default.md` is dennisworks-flavored and would publish the wrong voice to
mumblingpundit. Create `prompts-mumblingpundit/default.md` with a punditry
default (or leave the dir with only a `queue/`), so an empty-queue day is safe.

## 3. manual-poll.sh — parameterize for multiple backends (backward-compatible)
Current script hardcodes `.env`, `prompts/`, and one lock file. Make the env
file, prompts dir, and lock per-invocation; **no-arg calls behave exactly as
today**, so the existing dennisworks line is unaffected.

```sh
set -eu
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
PROMPTS_DIR="${2:-prompts}"
LOCK="/tmp/research-agents-manual-$(basename "$ENV_FILE").lock"

# grep instead of sourcing: .env values aren't guaranteed shell-safe.
url=$(grep -E '^(PUBLISH_URL|DWORKS_API_URL)=' "$ENV_FILE" | head -1 | cut -d= -f2-)
token=$(grep -E '^(PUBLISH_TOKEN|DWORKS_INGEST_TOKEN)=' "$ENV_FILE" | head -1 | cut -d= -f2-)

status=$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
  -H "Authorization: Bearer $token" "$url/api/research/prompt/manual")
[ "$status" = "200" ] || exit 0

echo "[manual-poll $(date -u +%FT%TZ)] pending run detected ($ENV_FILE)"
exec flock -n "$LOCK" \
  docker run --rm --env-file "$ENV_FILE" \
  -v "$(pwd)/$PROMPTS_DIR:/app/prompts" \
  research-agents --manual
```
(This is a genuine multi-backend improvement to the public repo — worth
committing upstream rather than keeping VPS-local.)

## 4. Crontab entries (append to `crontab -e` for `dennis`)
Keep the two existing dennisworks lines as-is. Add:

```cron
# mumblingpundit: daily article drafts at 06:10 UTC (10 min after dennisworks,
# so the 06:00 line has already git-pulled + rebuilt the shared image).
10 6 * * * cd /home/dennis/sites/research-agents && docker run --rm --env-file .env.mumblingpundit -v /home/dennis/sites/research-agents/prompts-mumblingpundit:/app/prompts research-agents >> /home/dennis/research-agents-mumblingpundit.log 2>&1

# mumblingpundit: poll for "Run now" requests (its own env file + lock).
* * * * * /home/dennis/sites/research-agents/scripts/manual-poll.sh .env.mumblingpundit prompts-mumblingpundit >> /home/dennis/research-agents-manual-mumblingpundit.log 2>&1
```

Why 06:10 and not a second build: the 06:00 dennisworks line already does
`git pull --ff-only && docker build -q -t research-agents .`, so the image is
fresh when mumblingpundit runs. If you ever disable the dennisworks daily line,
move the pull+build into a shared step (see §5) so mumblingpundit still gets a
current image.

## 5. Optional cleaner refactor — one build, fan out to both sites
Replaces both daily lines with a single script + one crontab line. Prevents the
"mumblingpundit depends on dennisworks' build step" coupling.

`scripts/run-daily.sh`:
```sh
#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
git pull --ff-only
docker build -q -t research-agents .
# site:env-file:prompts-dir
for spec in \
  "dennisworks:.env:prompts" \
  "mumblingpundit:.env.mumblingpundit:prompts-mumblingpundit"; do
  site=${spec%%:*}; rest=${spec#*:}; env=${rest%%:*}; prompts=${rest#*:}
  echo "[run-daily $(date -u +%FT%TZ)] $site"
  docker run --rm --env-file "$env" \
    -v "$(pwd)/$prompts:/app/prompts" research-agents \
    >> "/home/dennis/research-agents-$site.log" 2>&1 || \
    echo "[run-daily] $site FAILED"
done
```
Crontab (replaces both daily lines):
```cron
0 6 * * * /home/dennis/sites/research-agents/scripts/run-daily.sh
```

## 6. Verify (after endpoints are live)
```sh
# One-off dry run against mumblingpundit staging, no publish:
cd /home/dennis/sites/research-agents
docker run --rm --env-file .env.mumblingpundit research-agents --topic "test" --dry-run
# Live manual run — then confirm the draft at mumblingpundit /admin/research:
docker run --rm --env-file .env.mumblingpundit -v "$PWD/prompts-mumblingpundit:/app/prompts" research-agents --manual
```
