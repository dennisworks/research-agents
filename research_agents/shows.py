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

This module is graph-only: it returns structured objects and does not publish.
A shows sink / backend contract (the equivalent of sinks.py for articles) is
still to be designed — see the module TODO at the bottom.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_tavily import TavilySearch
from pydantic import BaseModel

from . import config
from .llm import make_llm, text_of
from .shows_schemas import ShowList, Venue, VenueList

VENUE_RESEARCH_PROMPT = """You are a local live-music researcher. Use the search
tool to find music venues and clubs that host live shows in the region you are
given. Run several distinct searches from different angles — e.g. "live music
venues in <region>", genre-specific clubs (jazz, rock, folk, metal), local
alt-weekly and events-calendar listings, and "concerts this month <region>".
Prefer venues that are currently operating and regularly program live music.
Then write research notes: for each venue list its name, city, website or
calendar URL, the genres it tends to host, and the source URL where you found
it. Only include real venues supported by the search results."""

VENUE_EXTRACT_PROMPT = """You turn venue research notes into a structured venue
list. Do not invent venues or URLs beyond what the notes contain. Every venue
must carry a source_url drawn from the notes. Drop anything you cannot ground in
the notes."""

SHOW_RESEARCH_PROMPT = """You are a live-music listings researcher. You are given
a region and a set of venues. Use the search tool to find upcoming, scheduled
shows at those venues — check each venue's events/calendar page and ticketing
listings. Capture the performing act(s), the venue, the date, the start/doors
time, the price, and a ticket link, along with the source URL each listing came
from. Run separate searches per venue where needed. Only include shows you can
actually find with a supporting source; do not guess dates."""

SHOW_EXTRACT_PROMPT = """You turn show research notes into a structured show list.
Normalize dates to ISO 8601 (YYYY-MM-DD); if a date is unknown, leave it null
rather than guessing. Do not invent shows, dates, or ticket links beyond what
the notes contain. Every show must carry a source_url drawn from the notes."""


def _research(system_prompt: str, request: str, *, max_results: int = 5) -> str:
    """Run a ReAct search agent for one stage; return its final notes."""
    search = TavilySearch(max_results=max_results)
    agent = create_agent(make_llm(), [search], system_prompt=system_prompt)
    result = agent.invoke({"messages": [("user", request)]})
    return text_of(result["messages"][-1].content)


def _extract(schema: type[BaseModel], system_prompt: str, request: str) -> BaseModel:
    """Turn notes into a structured object.

    Retried once: the structured-output call occasionally returns an incomplete
    object (Pydantic validation error), and a failed run means no listings.
    """
    llm = make_llm()
    method = config.structured_method()
    extractor = (
        llm.with_structured_output(schema, method=method)
        if method
        else llm.with_structured_output(schema)
    )
    messages = [("system", system_prompt), ("user", request)]
    try:
        return extractor.invoke(messages)
    except Exception:
        return extractor.invoke(messages)


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
    """Research scheduled shows at the given venues and return them structured."""
    notes = _research(
        SHOW_RESEARCH_PROMPT,
        f"Region: {region}\n\nFind upcoming shows at these venues:\n\n{_format_venues(venues)}",
    )
    request = f"Region: {region}\n\nShow research notes:\n\n{notes}"
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


def main() -> int:
    """Ad-hoc runner: research venues + shows for a region, print JSON.

    Graph-only for now (no sink) — this prints results to stdout so the graph
    can be exercised end to end from the CLI:

        python -m research_agents.shows --region "Austin, TX"
    """
    import argparse
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Research venues + shows for a region.")
    parser.add_argument("--region", required=True, help='e.g. "Austin, TX"')
    parser.add_argument(
        "--venues-only",
        action="store_true",
        help="discover venues and stop (skip show gathering)",
    )
    args = parser.parse_args()

    if args.venues_only:
        venues = discover_venues(args.region)
        print(venues.model_dump_json(indent=2))
        return 0

    discovered, shows = run(args.region)
    out = {
        "venues": discovered.model_dump() if discovered else None,
        "shows": shows.model_dump(),
    }
    import json

    print(json.dumps(out, indent=2))
    print(
        f"[shows] {len(shows.shows)} show(s) across "
        f"{len(discovered.venues) if discovered else 0} venue(s)",
        file=sys.stderr,
    )
    return 0


# TODO(sink): articles publish via research_agents.sinks (FileSink / WebhookSink
# → POST /api/research/ingest). Shows are a different artifact and need their own
# sink — likely POST /api/shows/ingest on the mumblingpundit backend, with
# per-show upsert/dedupe keyed on (venue, date, artist) rather than slug. Add it
# once the backend endpoint contract exists.


if __name__ == "__main__":
    raise SystemExit(main())
