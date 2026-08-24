"""Structured shapes for the shows graph (see shows.py).

Kept separate from schemas.py (the Article artifact) because a show listing is
a different artifact entirely: structured event records, not prose. The graph
produces a VenueList (which clubs exist in a region) and a ShowList (what's
playing at them).
"""

from datetime import date as _date

from pydantic import BaseModel, Field, field_validator


class Venue(BaseModel):
    """A live-music venue discovered for a region."""

    name: str
    city: str = Field(description="city/town the venue is in")
    url: str | None = Field(
        default=None, description="official site or events/calendar page, if found"
    )
    genres: list[str] = Field(
        default_factory=list, description="music styles the venue typically hosts"
    )
    notes: str | None = Field(default=None, description="one-line description of the venue")
    source_url: str = Field(description="the page this venue was found on")


class VenueList(BaseModel):
    region: str = Field(description="the area these venues serve, e.g. 'Austin, TX'")
    venues: list[Venue]


class Show(BaseModel):
    """A single scheduled show at a venue."""

    artist: str = Field(description="headliner / performing act(s)")
    venue: str = Field(description="venue name")
    city: str | None = None
    date: str | None = Field(
        default=None, description="ISO 8601 date (YYYY-MM-DD) when known; null if unknown"
    )
    time: str | None = Field(
        default=None, description="local start/doors time, e.g. '20:00' or '8pm doors'"
    )
    price: str | None = Field(default=None, description="ticket price or range, as listed")
    ticket_url: str | None = Field(default=None, description="link to buy/RSVP, if found")
    description: str | None = Field(default=None, description="support acts, genre, or other notes")
    source_url: str = Field(description="the listing page this show was drawn from")

    @field_validator("date")
    @classmethod
    def _canonical_iso_date(cls, v: str | None) -> str | None:
        """Guarantee `date` is a canonical YYYY-MM-DD or None. The model is
        asked for ISO dates but `str` would accept anything (e.g. "Friday, Aug
        28"); a non-ISO value is dropped to None so downstream dedupe on
        (venue, date, artist) never keys off an ambiguous string."""
        if v is None:
            return None
        try:
            return _date.fromisoformat(v).isoformat()
        except ValueError:
            return None


class ShowList(BaseModel):
    region: str
    shows: list[Show]
