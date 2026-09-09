# mumblingpundit as a second publish backend (VPS)

mumblingpundit publishes through the **same `research-agents` image and repo** as
dennisworks — it's just a second env file, a second prompts dir, and a second
"Run now" poll line. This is **live** on the VPS (user `dennis`, plain crontab).

> **Drafts are on-demand, not scheduled.** There is no daily *draft* cron for
> either site. You generate a draft from `/admin/research` ("Run now") or the
> deploy-monitor Agents tab, review it in the queue, and publish. Cron does only
> two things now: (a) keep the shared image fresh, and (b) poll for "Run now"
> requests. See §4.

## 1. Env file — `/home/dennis/sites/research-agents/.env.mumblingpundit`
Reuses the shared Anthropic/Tavily keys; only the backend + token differ.
```
ANTHROPIC_API_KEY=<same value as .env>
TAVILY_API_KEY=<same value as .env>
PROMPT_TZ=UTC
PUBLISH_URL=<mumblingpundit production URL>
PUBLISH_TOKEN=<must equal mumblingpundit's CRON_SECRET>
```

## 2. Dedicated prompts fallback — `prompts-mumblingpundit/`
mumblingpundit's briefs live in its **own DB queue** (served by
`/api/research/prompt`), which resolves first. The mounted prompts dir is only a
fallback for when the queue is empty. Do **not** mount the shared `prompts/` —
its `default.md` is dennisworks-flavored and would publish the wrong voice to
mumblingpundit. `prompts-mumblingpundit/` carries a punditry `default.md` (plus a
`queue/`), so an empty-queue day is safe.

## 3. manual-poll.sh (shipped, multi-backend)
`scripts/manual-poll.sh` takes the env file + prompts dir as positional args, so
one script serves every backend; a **no-arg call is the dennisworks default**
(`.env` + `prompts/`). It checks `<PUBLISH_URL>/api/research/prompt/manual`, and
on a pending request runs `docker run … research-agents --manual` under a
per-backend `flock`. Nothing here is mumblingpundit-specific except the args in
its crontab line (§4).

## 4. Crontab (user `dennis`, `crontab -e`) — current state
No daily *draft* lines. One **build-only** line keeps the shared image current
for every on-demand run (both the `/admin/research` button and the Agents tab);
two **poll** lines power "Run now" for each backend:

```cron
# research-agents: keep the shared image fresh daily (drafts are on-demand, not scheduled)
0 6 * * * cd /home/dennis/sites/research-agents && git pull --ff-only && docker build -q -t research-agents . >> /home/dennis/research-agents-build.log 2>&1

# dennisworks: poll for "Run now" requests from /admin/research/prompts
* * * * * /home/dennis/sites/research-agents/scripts/manual-poll.sh >> /home/dennis/research-agents-manual.log 2>&1

# mumblingpundit: poll for "Run now" requests (its own env file + prompts + lock)
* * * * * /home/dennis/sites/research-agents/scripts/manual-poll.sh .env.mumblingpundit prompts-mumblingpundit >> /home/dennis/research-agents-manual-mumblingpundit.log 2>&1
```

**Why a build-only line:** the retired 06:00/06:10 lines did `git pull --ff-only
&& docker build` *and then* ran a draft. The draft is now on-demand, but the
pull+build still has to happen somewhere — otherwise every on-demand run (admin
button *and* Agents tab) silently drifts onto stale code. So the refresh survives
as its own line. (The shows cron in `shows-backend-cron.md` still relies on this
06:00 line having refreshed the image before it runs.)

## 5. Verify
```sh
cd /home/dennis/sites/research-agents
# Dry run against mumblingpundit, no publish:
docker run --rm --env-file .env.mumblingpundit research-agents --topic "test" --dry-run
# Live manual run — then confirm the draft at mumblingpundit /admin/research:
docker run --rm --env-file .env.mumblingpundit -v "$PWD/prompts-mumblingpundit:/app/prompts" research-agents --manual
```

## History
Originally this backend also ran a **daily 06:10 UTC draft** (10 min after the
dennisworks 06:00 line, to reuse its fresh image). Both sites' daily drafts were
**retired 2026-09-09** in favor of on-demand generation + editorial review; the
pull+build was split into the standalone refresh line above.
