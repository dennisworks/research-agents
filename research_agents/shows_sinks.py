"""Where a finished ShowList goes.

The article sink (sinks.py) POSTs one Article to /api/research/ingest and treats
a 409 as a duplicate. Shows are different: a whole region's ShowList is POSTed as
one batch to /api/shows/ingest, and the backend UPSERTs on (region, venue, date,
artist) — re-running a region is expected and never 409s. See
docs/shows-backend-handoff.md for the agreed contract.

Backend selection reuses config.publish_backend() (PUBLISH_URL + PUBLISH_TOKEN),
the same env the article pipeline uses; only the path differs. With no backend
configured get_show_sink() returns None and the caller just prints the batch.
"""

from __future__ import annotations

import sys

import httpx

from . import config
from .shows_schemas import Show, ShowList


class IngestError(Exception):
    """The backend rejected the batch (401 auth, or 400 validation). The batch
    is all-or-nothing: a 400 means nothing was stored, so fix and resend."""


def _looks_like_url(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _sanitize(shows: list[Show]) -> tuple[list[Show], int]:
    """Make a batch safe to send. The backend rejects the ENTIRE batch on the
    first bad field, so drop entries that would 400 rather than lose the whole
    region: a show needs a non-empty artist + venue and a URL source_url. A
    non-URL ticket_url is nulled (optional field, not worth dropping the show).
    Also de-duplicates within the batch on (venue, date, artist) — the backend
    would count repeats as "skipped"; sending them once is cleaner.
    Returns (kept, dropped_count)."""
    kept: list[Show] = []
    seen: set[tuple[str, str | None, str]] = set()
    dropped = 0
    for s in shows:
        if not (s.artist and s.venue) or not _looks_like_url(s.source_url):
            dropped += 1
            continue
        key = (s.venue, s.date, s.artist)
        if key in seen:
            continue  # intra-batch duplicate; backend would skip it anyway
        seen.add(key)
        if not _looks_like_url(s.ticket_url):
            s = s.model_copy(update={"ticket_url": None})
        kept.append(s)
    return kept, dropped


class ShowWebhookSink:
    """POST a ShowList batch to /api/shows/ingest (bearer auth, upsert)."""

    def __init__(self, base_url: str, token: str):
        self.base = base_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def publish(self, batch: ShowList) -> dict:
        """Send one region's shows. Returns the backend's {created, updated,
        skipped} counts. Raises IngestError on 401/400."""
        kept, dropped = _sanitize(batch.shows)
        if dropped:
            print(f"[shows] dropped {dropped} unpublishable show(s) before send", file=sys.stderr)
        payload = ShowList(region=batch.region, shows=kept).model_dump()
        resp = httpx.post(
            f"{self.base}/api/shows/ingest",
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        if resp.status_code == 401:
            raise IngestError("unauthorized — check PUBLISH_TOKEN matches the backend CRON_SECRET")
        if resp.status_code == 400:
            raise IngestError(f"batch rejected (400, nothing stored): {resp.text}")
        resp.raise_for_status()
        return resp.json()


def get_show_sink() -> ShowWebhookSink | None:
    """ShowWebhookSink when a publish backend is configured, else None."""
    backend = config.publish_backend()
    return ShowWebhookSink(*backend) if backend else None
