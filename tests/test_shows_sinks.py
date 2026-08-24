import httpx
import pytest

from research_agents.shows_schemas import Show, ShowList
from research_agents.shows_sinks import (
    IngestError,
    ShowWebhookSink,
    _sanitize,
    get_show_sink,
)

_BACKEND_KEYS = ("PUBLISH_URL", "PUBLISH_TOKEN", "DWORKS_API_URL", "DWORKS_INGEST_TOKEN")


def _show(**over):
    base = dict(artist="A", venue="V", source_url="https://ex.com/listing")
    base.update(over)
    return Show(**base)


class _FakeResp:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


# --- get_show_sink selection ----------------------------------------------


def test_get_show_sink_none_without_backend(monkeypatch):
    for key in _BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert get_show_sink() is None


def test_get_show_sink_webhook_when_backend_set(monkeypatch):
    monkeypatch.setenv("PUBLISH_URL", "http://backend")
    monkeypatch.setenv("PUBLISH_TOKEN", "tok")
    assert isinstance(get_show_sink(), ShowWebhookSink)


# --- publish payload + response -------------------------------------------


def test_publish_posts_batch_and_returns_counts(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers)
        return _FakeResp(200, {"created": 1, "updated": 0, "skipped": 0})

    monkeypatch.setattr(httpx, "post", fake_post)

    batch = ShowList(region="Austin, TX", shows=[_show(date="2026-09-14")])
    counts = ShowWebhookSink("http://backend", "tok").publish(batch)

    assert counts == {"created": 1, "updated": 0, "skipped": 0}
    assert captured["url"] == "http://backend/api/shows/ingest"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"]["region"] == "Austin, TX"
    assert captured["json"]["shows"][0]["artist"] == "A"


def test_publish_raises_on_401(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp(401, text="no"))
    with pytest.raises(IngestError, match="unauthorized"):
        ShowWebhookSink("http://backend", "tok").publish(ShowList(region="X", shows=[_show()]))


def test_publish_raises_on_400_batch_rejected(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp(400, text="bad date"))
    with pytest.raises(IngestError, match="batch rejected"):
        ShowWebhookSink("http://backend", "tok").publish(ShowList(region="X", shows=[_show()]))


# --- sanitize --------------------------------------------------------------


def test_sanitize_drops_missing_required_and_bad_source_url():
    shows = [
        _show(),  # keep
        _show(artist=""),  # drop: no artist
        _show(source_url="not-a-url"),  # drop: source_url not a URL
    ]
    kept, dropped = _sanitize(shows)
    assert dropped == 2
    assert len(kept) == 1


def test_sanitize_nulls_bad_ticket_url_but_keeps_show():
    kept, dropped = _sanitize([_show(ticket_url="buy-here")])
    assert dropped == 0
    assert kept[0].ticket_url is None


def test_sanitize_dedupes_within_batch_on_venue_date_artist():
    shows = [
        _show(date="2026-09-14"),
        _show(date="2026-09-14"),  # exact dup key -> collapsed
        _show(date=None),  # null date is a distinct key -> kept
    ]
    kept, _ = _sanitize(shows)
    assert len(kept) == 2


def test_publish_skips_sending_dropped_shows(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(json=json)
        return _FakeResp(200, {"created": 1, "updated": 0, "skipped": 0})

    monkeypatch.setattr(httpx, "post", fake_post)

    batch = ShowList(region="X", shows=[_show(), _show(source_url="nope")])
    ShowWebhookSink("http://backend", "tok").publish(batch)
    assert len(captured["json"]["shows"]) == 1  # the bad one never left the client
