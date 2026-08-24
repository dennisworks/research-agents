"""Two-stage shows pipeline for a region.

We don't start from a known venue list — the pipeline researches that too:

1. discover_venues(region)  — a ReAct agent (chat model + Tavily) hunts for
   live-music clubs in the region, then a structured-output call turns the
   notes into a VenueList.
2. gather_shows(region, venues) — a second ReAct agent works the discovered
   venues' calendars, then a structured-output call turns the notes into a
   ShowList.

run(region) chains both. Pass an explicit `venues=` to skip discovery once you
have a curated list (e.g. a pinned set for a region you already trust).

Both stages reuse the same model/config plumbing as the article pipeline
(research_agents.llm + research_agents.config), so RESEARCH_MODEL, the prompt
cache, and RESEARCH_STRUCTURED_METHOD all apply here unchanged.

run() is pure — it returns structured objects and does not publish. Publishing
is a separate step (see main() and shows_sinks.ShowWebhookSink → POST
/api/shows/ingest), mirroring how the article pipeline keeps agent.run separate
from sinks.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_tavily import TavilySearch
from pydantic import BaseModel, ValidationError

from . import config
from .llm import make_llm, structured_invoke, text_of
from .shows_schemas import ShowList, Venue, VenueList

VENUE_RESEARCH_PROMPT = """You are a local live-music researcher. Use the search
tool to find music venues and clubs that host live shows in the region you are
given. Treat the region as a strict geographic boundary: it may name a city, a
side of a city, or a specific set of neighborhoods, and you should only look for
venues physically located inside it — ignore venues outside it even when a
search surfaces them. Run several distinct searches from different angles — e.g.
"live music venues in <region>", genre-specific clubs (jazz, rock, folk, metal),
local alt-weekly and events-calendar listings, and "concerts this month
<region>". Prefer venues that are currently operating and regularly program live
music. Then write research notes: for each venue list its name, the city or town
it is in (put any neighborhood or district detail in a short note, not the city),
website or calendar URL, the genres it tends to host, and the source URL where
you found it. Only include real venues supported by the search results, and only
ones inside the region."""

VENUE_EXTRACT_PROMPT = """You turn venue research notes into a structured venue
list. The request states the target region — include ONLY venues physically
located within it, and drop any venue outside that region even if it appears in
the notes. Keep `city` as the city or town; put neighborhood/district detail in
`notes`, not in `city`. Do not invent venues or URLs beyond what the notes
contain. Every venue must carry a source_url drawn from the notes. Drop anything
you cannot ground in the notes."""

SHOW_RESEARCH_PROMPT = """You are a live-music listings researcher. You are given
a region and a set of venues. Use the search tool to find upcoming, scheduled
shows at those venues — check each venue's events/calendar page and ticketing
listings. Capture the performing act(s), the venue, the date, the start/doors
time, the price, and a ticket link, along with the source URL each listing came
from. Run separate searches per venue where needed. Only include shows you can
actually find with a supporting source; do not guess dates."""

SHOW_EXTRACT_PROMPT = """You turn show research notes into a structured show list.
The request lists the venues in scope; include ONLY shows taking place at one of
those venues and drop any show whose venue is not in that list. Normalize dates
to ISO 8601 (YYYY-MM-DD); if a date is unknown, leave it null rather than
guessing. Do not invent shows, dates, or ticket links beyond what the notes
contain. Every show must carry a source_url drawn from the notes."""


def _research(system_prompt: str, request: str, *, max_results: int = 5) -> str:
    """Run a ReAct search agent for one stage; return its final notes."""
    search = TavilySearch(max_results=max_results)
    agent = create_agent(make_llm(), [search], system_prompt=system_prompt)
    result = agent.invoke({"messages": [("user", request)]})
    return text_of(result["messages"][-1].content)


def _extract(schema: type[BaseModel], system_prompt: str, request: str) -> BaseModel:
    """Turn notes into a structured object.

    Retried once on a malformed structured result (see structured_invoke); a
    failed run means no listings that cycle.
    """
    messages = [("system", system_prompt), ("user", request)]
    return structured_invoke(make_llm(), schema, messages, method=config.structured_method())


def discover_venues(region: str) -> VenueList:
    """Research live-music venues in `region` and return them structured."""
    notes = _research(
        VENUE_RESEARCH_PROMPT,
        f"Find live-music venues in this region:\n\n{region}",
    )
    request = f"Region: {region}\n\nVenue research notes:\n\n{notes}"
    result = _extract(VenueList, VENUE_EXTRACT_PROMPT, request)
    return result  # type: ignore[return-value]


def _format_venues(venues: list[Venue]) -> str:
    lines = []
    for v in venues:
        url = f" — {v.url}" if v.url else ""
        genres = f" [{', '.join(v.genres)}]" if v.genres else ""
        lines.append(f"- {v.name} ({v.city}){url}{genres}")
    return "\n".join(lines)


def gather_shows(region: str, venues: list[Venue]) -> ShowList:
    """Research scheduled shows at the given venues and return them structured.

    With no venues there is nothing to search, and running the researcher on an
    empty venue set would let it surface shows for arbitrary venues — so
    short-circuit to an empty result instead.
    """
    if not venues:
        return ShowList(region=region, shows=[])
    venue_block = _format_venues(venues)
    notes = _research(
        SHOW_RESEARCH_PROMPT,
        f"Region: {region}\n\nFind upcoming shows at these venues:\n\n{venue_block}",
    )
    # Carry the venue list into the extraction request too (not just the free-form
    # notes), so the extractor can enforce that every show belongs to this set.
    request = (
        f"Region: {region}\n\nVenues in scope (include only shows at these):\n"
        f"{venue_block}\n\nShow research notes:\n\n{notes}"
    )
    result = _extract(ShowList, SHOW_EXTRACT_PROMPT, request)
    return result  # type: ignore[return-value]


def run(region: str, venues: list[Venue] | None = None) -> tuple[VenueList | None, ShowList]:
    """Full pipeline for a region.

    With no `venues`, discovers them first and returns the VenueList alongside
    the shows. Pass a curated `venues` list to skip discovery (the returned
    VenueList is then None).
    """
    discovered: VenueList | None = None
    if venues is None:
        discovered = discover_venues(region)
        venues = discovered.venues
    shows = gather_shows(region, venues)
    return discovered, shows


def _load_venues(path: str) -> list[Venue]:
    """Load a curated venue list to run against instead of discovering.

    Accepts either a VenueList dump ({"region": ..., "venues": [...]} — exactly
    what --venues-only prints) or a bare list of venue objects. Bootstrap flow:
    run --venues-only for a region, prune the output to the venues you want, then
    pass that file back here to pin the run to those venues.

    Raises ValueError with a readable message on any bad input (missing/unreadable
    file, invalid JSON, wrong shape, or a malformed venue) so the CLI can report
    it cleanly instead of dumping a traceback.
    """
    import json
    from pathlib import Path

    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"could not read venues file {path!r}: {e}") from e

    if isinstance(data, dict):
        raw = data.get("venues")
    elif isinstance(data, list):
        raw = data
    else:
        raw = None
    if not isinstance(raw, list):
        raise ValueError(
            f"venues file {path!r} must be a VenueList dump "
            '({"region": ..., "venues": [...]}) or a list of venue objects'
        )

    try:
        return [Venue.model_validate(v) for v in raw]
    except ValidationError as e:
        raise ValueError(f"invalid venue in {path!r}: {e}") from e


def main() -> int:
    """Ad-hoc runner: research venues + shows for a region, then publish.

    When a backend is configured (PUBLISH_URL + PUBLISH_TOKEN) the shows are
    POSTed to it and the ingest counts are logged; otherwise (or with --dry-run)
    the batch is printed as JSON so the graph can be exercised without a backend:

        python -m research_agents.shows --region "Austin, TX"
    """
    import argparse
    import json
    import sys

    from dotenv import load_dotenv

    from .shows_sinks import IngestError, get_show_sink

    load_dotenv()
    parser = argparse.ArgumentParser(description="Research venues + shows for a region.")
    parser.add_argument("--region", required=True, help='e.g. "Austin, TX"')
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--venues-only",
        action="store_true",
        help="discover venues and stop (skip show gathering)",
    )
    source.add_argument(
        "--venues",
        metavar="PATH",
        help=(
            "run against a curated venue list (JSON as printed by --venues-only, "
            "pruned to the venues you want); skips discovery"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the batch as JSON instead of publishing, even if a backend is set",
    )
    args = parser.parse_args()

    if args.venues_only:
        # Venue persistence is not part of phase 1 — venues only ever print.
        venues = discover_venues(args.region)
        print(venues.model_dump_json(indent=2))
        return 0

    pinned = None
    if args.venues:
        try:
            pinned = _load_venues(args.venues)
        except ValueError as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1

    discovered, shows = run(args.region, venues=pinned)
    venue_count = (
        len(pinned) if pinned is not None else (len(discovered.venues) if discovered else 0)
    )
    print(
        f"[shows] gathered {len(shows.shows)} show(s) across {venue_count} venue(s)"
        + (" (curated list)" if pinned is not None else ""),
        file=sys.stderr,
    )

    sink = None if args.dry_run else get_show_sink()
    if sink is None:
        if discovered is not None:
            venues_out = discovered.model_dump()
        elif pinned is not None:
            venues_out = VenueList(region=args.region, venues=pinned).model_dump()
        else:
            venues_out = None
        out = {"venues": venues_out, "shows": shows.model_dump()}
        print(json.dumps(out, indent=2))
        return 0

    try:
        counts = sink.publish(shows)
    except IngestError as e:
        print(f"[error] shows ingest failed: {e}", file=sys.stderr)
        return 1
    print(f"[published] {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
