# Shows cron — publishing live-music listings to mumblingpundit (VPS)

Parallels `mumblingpundit-backend-cron.md` (the article backend) but for the
**shows** graph. Two differences that matter:

- Shows is **region-driven, not prompt-driven** → no `prompts/` mount, and **no
  manual-poll line** (there's no "Run now" queue for shows).
- The image `ENTRYPOINT` is `uv run --no-sync python main.py` (the article
  pipeline), so the shows cron **overrides the entrypoint** to run the shows
  module instead.

Runs as user `dennis` on the VPS. Reuses the same Docker image + repo; it's one
env file + one daily crontab line. Requires the shows graph + sink + region
scoping to be in the built image: `ShowSink` (PR #9, `ba7c71f`) and region
scoping + `--venues` (PR #10, `9f96ab8`).

## 1. Pull + build (first time / manual test)

The 06:00 dennisworks cron already does `git pull --ff-only && docker build`, so
normally the image is fresh. For the first manual test, do it by hand:

```sh
cd /home/dennis/sites/research-agents
git pull --ff-only
docker build -q -t research-agents .
```

## 2. Env file — `/home/dennis/sites/research-agents/.env.shows`

Reuses the shared Anthropic/Tavily keys from `.env`; only the backend + token
differ. This pulls the two keys from the existing `.env` and prompts for the
secret so it never lands in shell history:

```sh
cd /home/dennis/sites/research-agents
read -rsp 'mumblingpundit CRON_SECRET: ' MP_CRON_SECRET; echo
{
  grep -E '^(ANTHROPIC_API_KEY|TAVILY_API_KEY)=' .env
  echo 'PUBLISH_URL=https://mumblingpundit.vercel.app'
  echo "PUBLISH_TOKEN=$MP_CRON_SECRET"
  echo '# A full metro show list overruns the 8000-token default and truncates the'
  echo '# structured output; opus-4-8 supports far more, so give the extraction room.'
  echo 'RESEARCH_MAX_TOKENS=32000'
  echo 'RESEARCH_TIMEOUT=600'
} > .env.shows
chmod 600 .env.shows
unset MP_CRON_SECRET
```

The `RESEARCH_MAX_TOKENS` bump matters: the show-extraction step emits the whole
region's `ShowList` in one structured call, and the 8000-token default truncates
it (the run fails with a Pydantic validation error after an `Output parser
received a max_tokens stop reason` warning). Scoping the region (below) and/or a
curated `--venues` list also shrink the output, but keep the headroom.

## 3. Choose the region — scope the listings

`--region` is free-text that drives venue discovery, and the venue prompts treat
it as a strict geographic boundary. To limit the feed to one part of a city, name
the neighborhoods and the exclusions explicitly. Set it once as a shell var for
the verify steps below (mumblingpundit is Chicago-flavored — PR #7):

```sh
REGION="the North and Northwest Sides of Chicago, IL — neighborhoods including Lincoln Park, Lakeview, Wrigleyville, Uptown, Edgewater, Andersonville, Rogers Park, Lincoln Square, North Center, Roscoe Village, Avondale, Logan Square, Irving Park, Albany Park, Portage Park, Jefferson Park. EXCLUDE the Loop, West Loop, Pilsen, the South and West Sides, and suburbs."
```

This is a *soft* filter — strong prompt adherence, but discovery can still miss.
For a **hard** guarantee (no drift), pin a curated venue list and skip discovery.
Bootstrap it once, then reuse the file:

```sh
# Discover for the scoped region, then hand-prune the file to the venues you want:
docker run --rm --entrypoint uv --env-file .env.shows research-agents \
  run --no-sync python -m research_agents.shows --region "$REGION" --venues-only \
  > venues.json
$EDITOR venues.json                     # delete any venue that isn't north/NW side
```

`--venues venues.json` (used below) then runs only those venues.

## 4. Verify before scheduling

```sh
cd /home/dennis/sites/research-agents

# a) Auth preflight — empty batch, valid token. Expect 200 {"created":0,...};
#    writes nothing. A 401 means the token doesn't match mumblingpundit's CRON_SECRET.
url=$(grep '^PUBLISH_URL='   .env.shows | cut -d= -f2-)
tok=$(grep '^PUBLISH_TOKEN=' .env.shows | cut -d= -f2-)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$url/api/shows/ingest" \
  -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
  -d '{"region":"__preflight__","shows":[]}'

# b) Dry run — full research for the scoped region, prints JSON, publishes nothing.
docker run --rm --entrypoint uv --env-file .env.shows research-agents \
  run --no-sync python -m research_agents.shows --region "$REGION" --dry-run

#    …or against the curated list (hard-scoped, skips discovery):
docker run --rm --entrypoint uv --env-file .env.shows \
  -v "$PWD/venues.json:/app/venues.json:ro" research-agents \
  run --no-sync python -m research_agents.shows --region "$REGION" \
  --venues /app/venues.json --dry-run

# c) Live run — research + publish, prints [published] {created,updated,skipped}.
#    Then confirm the listings on mumblingpundit's shows page. Drop --dry-run:
docker run --rm --entrypoint uv --env-file .env.shows research-agents \
  run --no-sync python -m research_agents.shows --region "$REGION"
```

Note the curated-list run **mounts** `venues.json` into the container (`-v`) —
the repo checkout isn't the container's filesystem, so the file has to be mounted
at a path the process can read.

## 5. Crontab entry (append via `crontab -e` for `dennis`)

Keep the existing dennisworks + mumblingpundit article lines as-is. Add one daily
shows line at 06:20 UTC (after the 06:00 build has refreshed the image). The
region string is inlined here — cron has no shell vars:

```cron
# mumblingpundit: daily north/NW-side Chicago live-music shows at 06:20 UTC (after
# the 06:00 dennisworks line has git-pulled + rebuilt the shared image). No prompts
# mount, no manual-poll — shows is region-driven. Entrypoint overridden to run the
# shows module instead of main.py.
20 6 * * * cd /home/dennis/sites/research-agents && docker run --rm --entrypoint uv --env-file .env.shows research-agents run --no-sync python -m research_agents.shows --region "the North and Northwest Sides of Chicago, IL — Lincoln Park, Lakeview, Wrigleyville, Uptown, Edgewater, Andersonville, Rogers Park, Lincoln Square, North Center, Roscoe Village, Avondale, Logan Square, Irving Park, Albany Park, Portage Park, Jefferson Park; EXCLUDE the Loop, West Loop, Pilsen, the South and West Sides, and suburbs." >> /home/dennis/research-agents-shows.log 2>&1
```

**Curated-list variant (hard-scoped).** Mount the pruned `venues.json` and add
`--venues`; the region string is then just a label for the batch:

```cron
20 6 * * * cd /home/dennis/sites/research-agents && docker run --rm --entrypoint uv --env-file .env.shows -v /home/dennis/sites/research-agents/venues.json:/app/venues.json:ro research-agents run --no-sync python -m research_agents.shows --region "North/NW Chicago" --venues /app/venues.json >> /home/dennis/research-agents-shows.log 2>&1
```

## 6. Multiple regions

For more than one area, add one `docker run … --region "<name>"` per region on the
same line (`&&`-chained) or fold them into a small `run-shows.sh` loop, same shape
as the `run-daily.sh` fan-out in `mumblingpundit-backend-cron.md` §5.
