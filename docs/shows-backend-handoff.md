# Handoff — shows ingest backend (for the mumblingpundit container agent)

**From:** research-agents (shows graph, merged to `main` — see `research_agents/shows.py`)
**To:** the mumblingpundit container agent (owns the mumblingpundit codebase)
**Why this split:** mumblingpundit code is edited only by its own container agent, not
from the research-agents host session. This doc is the contract; you implement the
backend, I'll wire the matching sink on the graph side once we agree on it.

---

## Context

research-agents now has a **shows graph** (`research_agents/shows.py`) that mirrors the
article pipeline but produces a different artifact — structured live-music listings, not
prose. Two stages, both LLM + Tavily:

1. `discover_venues(region)` → `VenueList` (which clubs exist in a region)
2. `gather_shows(region, venues)` → `ShowList` (what's playing at them)

It's **graph-only today**: it returns objects and does not publish (`TODO(sink)` in
`shows.py`). The article pipeline publishes via `WebhookSink` → `POST /api/research/ingest`.
Shows need their **own** endpoint because the artifact and the dedupe semantics differ.

This handoff asks you to build that receiving endpoint (+ storage + display) in
mumblingpundit. Once the contract below is agreed, I'll add a `ShowSink` on the
research-agents side that POSTs to it and a `.env.shows` VPS cron entry (same pattern as
`docs/mumblingpundit-backend-cron.md`).

## What to build (phase 1 — shows ingest)

### Endpoint

```
POST /api/shows/ingest
Authorization: Bearer <token>     # token == mumblingpundit CRON_SECRET, same as /api/research/*
Content-Type: application/json
```

Body is a **`ShowList`** (one region's run, a batch of shows):

```jsonc
{
  "region": "Austin, TX",
  "shows": [
    {
      "artist": "The Band",          // headliner / performing act(s)  (required)
      "venue": "The Continental",    // venue name                      (required)
      "city": "Austin",              // nullable
      "date": "2026-09-14",          // canonical YYYY-MM-DD or null (graph guarantees ISO-or-null)
      "time": "8pm doors",           // nullable, free-form local time
      "price": "$20",                // nullable
      "ticket_url": "https://...",   // nullable
      "description": "w/ support",   // nullable
      "source_url": "https://..."    // listing page it came from        (required)
    }
  ]
}
```

Exact field set/types come from `research_agents/shows_schemas.py` (`Show` / `ShowList`).
`date` is already normalized graph-side: a field validator drops non-ISO strings to `null`,
so you never receive `"Friday, Aug 28"` — it's `YYYY-MM-DD` or `null`.

### Semantics — **upsert, not 409**

The article sink returns **409** on a duplicate slug (`DuplicateDraft`). Shows are the
opposite: runs re-run and should **update** existing records and **insert** new ones, never
error. So:

- **Dedupe/upsert key:** `(venue, date, artist)`. On conflict, update the mutable fields
  (time, price, ticket_url, description, city, source_url).
- **Idempotent:** re-POSTing the same batch changes nothing.
- **Response:** `200` with counts, e.g. `{ "created": 3, "updated": 5, "skipped": 0 }`.

### Suggested storage (mumblingpundit is Postgres)

A `shows` table with the `Show` fields + `region`, `created_at`, `updated_at`, and a
**unique constraint on `(venue, date, artist)`** to drive the upsert. ORM choice
(Prisma/Drizzle/whatever mumblingpundit already uses) is yours.

### Display (your call)

A page listing **upcoming** shows for a region (filter `date >= today`, nulls last or
hidden). Design/routing is mumblingpundit's decision — out of scope for this contract.

## Contract finalized (confirmed by the mumblingpundit agent)

All four leans adopted as-is. Confirmed/added detail:

1. **Null-date dedupe:** null is its own key — a `null`-date show dedupes only against other
   undated shows for the same `venue+artist`, never merges with a dated one. Send `null`
   only when the date is genuinely unknown.
2. **Batch per region:** one POST = one region's full `ShowList`. Response
   `200 {created, updated, skipped}`, where **`skipped` = intra-batch duplicate keys**
   (same `(venue, date, artist)` twice in one payload; first wins) — so de-dupe within a
   batch client-side where possible.
3. **Path/response:** `POST /api/shows/ingest` → `{created, updated, skipped}`, confirmed.
4. **No pruning backend-side:** send upcoming shows; display filters `date >= today`.
   Undated shows are shown under "Date TBA" rather than dropped.

Errors: **401** bad/missing token; **400** batch failed validation (missing required field,
malformed `source_url`/`ticket_url`, or non-`YYYY-MM-DD` date) — **whole batch rejected,
nothing stored**, so fix and resend. Partial batches are not accepted. Unique key in Postgres
is the 4-column `(region, venue, date, artist)`; null-date dedupe is enforced by a
find-then-write in the data layer (so ingest is not atomic against concurrent POSTs for the
same region — fine for a serial cron, noted as a phase-1 limitation).

**Sink implications (handled in `shows_sinks.py`):** because a single bad field rejects the
whole batch, the sink sanitizes before sending — drops shows missing `artist`/`venue` or with
a non-URL `source_url`, nulls a non-URL `ticket_url`, and de-dupes within the batch on
`(venue, date, artist)`. `date` is already ISO-or-null from the `Show` validator.

## Explicitly out of scope for phase 1

- **Venue persistence.** The graph also produces a `VenueList` during discovery. Persisting
  venues (so you can curate/pin a region and skip discovery) is a nice phase 2
  (`POST /api/venues/ingest`), not needed for shows to flow. Flag if you want it now.
- **Prompt/queue endpoints.** The article pipeline has `/api/research/prompt*` for a DB
  prompt queue. Shows are region-driven, not brief-driven; no queue needed yet.

## What happens on the research-agents side after you build this

1. Add a `ShowSink` (in `research_agents/sinks.py` or a sibling) that POSTs a `ShowList` to
   `/api/shows/ingest` with the bearer token, honoring your agreed response shape.
2. Wire it into `shows.run()` (replace the `TODO(sink)`).
3. Add a `.env.shows` + VPS crontab entry per `docs/shows-backend-cron.md`
   (reuses the same Docker image; new env file points `PUBLISH_URL` at mumblingpundit and
   sets the token to its `CRON_SECRET`). Note: unlike the article backends (now
   on-demand — see `docs/mumblingpundit-backend-cron.md`), shows is genuinely a
   daily scheduled job.

Ping back with answers to the open questions and I'll open the research-agents PR for the
sink against whatever you ship.
