from research_agents import shows
from research_agents.shows_schemas import Show, ShowList, Venue, VenueList


class _FakeExtractor:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


class _FakeLLM:
    def __init__(self, result, calls):
        self._result = result
        self._calls = calls

    def with_structured_output(self, schema, **kwargs):
        self._calls.append((schema, kwargs))
        return _FakeExtractor(self._result)


def test_extract_passes_structured_method_when_set(monkeypatch):
    calls = []
    result = VenueList(region="X", venues=[])
    monkeypatch.setattr(shows, "make_llm", lambda: _FakeLLM(result, calls))
    monkeypatch.setenv("RESEARCH_STRUCTURED_METHOD", "json_schema")
    out = shows._extract(VenueList, "sys", "req")
    assert out is result
    assert calls == [(VenueList, {"method": "json_schema"})]


def test_extract_omits_method_when_unset(monkeypatch):
    calls = []
    monkeypatch.setattr(shows, "make_llm", lambda: _FakeLLM(ShowList(region="X", shows=[]), calls))
    monkeypatch.delenv("RESEARCH_STRUCTURED_METHOD", raising=False)
    shows._extract(ShowList, "sys", "req")
    assert calls == [(ShowList, {})]


def test_run_skips_discovery_when_venues_given(monkeypatch):
    seen = {}

    def _fail_discover(region):  # discovery must not run
        seen["discovered"] = True
        return VenueList(region=region, venues=[])

    def _fake_gather(region, venues):
        seen["venues"] = venues
        return ShowList(region=region, shows=[])

    monkeypatch.setattr(shows, "discover_venues", _fail_discover)
    monkeypatch.setattr(shows, "gather_shows", _fake_gather)

    pinned = [Venue(name="Club", city="Austin", source_url="http://x")]
    discovered, show_list = shows.run("Austin, TX", venues=pinned)

    assert "discovered" not in seen  # discovery skipped
    assert seen["venues"] == pinned  # pinned venues fed straight to gathering
    assert discovered is None
    assert isinstance(show_list, ShowList)


def test_run_discovers_then_feeds_gathering(monkeypatch):
    v = Venue(name="Club", city="Austin", source_url="http://x")
    monkeypatch.setattr(
        shows, "discover_venues", lambda region: VenueList(region=region, venues=[v])
    )
    captured = {}

    def _fake_gather(region, venues):
        captured["venues"] = venues
        return ShowList(region=region, shows=[])

    monkeypatch.setattr(shows, "gather_shows", _fake_gather)

    discovered, _ = shows.run("Austin, TX")

    assert discovered is not None
    assert captured["venues"] == [v]  # discovered venues drive show gathering


def test_format_venues_is_readable():
    line = shows._format_venues(
        [
            Venue(
                name="The Continental",
                city="Austin",
                url="http://c",
                genres=["rock"],
                source_url="http://s",
            )
        ]
    )
    assert "The Continental" in line
    assert "Austin" in line
    assert "rock" in line


# --- stage seams: stub _research / _extract and assert what flows through -----


def test_discover_venues_wires_region_and_notes_through(monkeypatch):
    seen = {}

    def _fake_research(system_prompt, request, **kwargs):
        seen["research_request"] = request
        return "VENUE NOTES"

    def _fake_extract(schema, system_prompt, request):
        seen["extract"] = (schema, request)
        return VenueList(region="Austin, TX", venues=[])

    monkeypatch.setattr(shows, "_research", _fake_research)
    monkeypatch.setattr(shows, "_extract", _fake_extract)

    out = shows.discover_venues("Austin, TX")

    assert "Austin, TX" in seen["research_request"]  # region reaches the researcher
    assert seen["extract"][0] is VenueList  # extracts into the venue schema
    assert "VENUE NOTES" in seen["extract"][1]  # research notes reach extraction
    assert isinstance(out, VenueList)


def test_gather_shows_puts_venue_context_in_research_and_extraction(monkeypatch):
    seen = {}

    def _fake_research(system_prompt, request, **kwargs):
        seen["research_request"] = request
        return "SHOW NOTES"

    def _fake_extract(schema, system_prompt, request):
        seen["extract"] = (schema, request)
        return ShowList(region="Austin, TX", shows=[])

    monkeypatch.setattr(shows, "_research", _fake_research)
    monkeypatch.setattr(shows, "_extract", _fake_extract)

    venues = [Venue(name="The Continental", city="Austin", source_url="http://s")]
    shows.gather_shows("Austin, TX", venues)

    assert "The Continental" in seen["research_request"]  # venues drive the search
    assert seen["extract"][0] is ShowList
    assert "The Continental" in seen["extract"][1]  # venue set constrains extraction
    assert "SHOW NOTES" in seen["extract"][1]


def test_gather_shows_short_circuits_on_empty_venues(monkeypatch):
    called = {"research": False}

    def _fail_research(*args, **kwargs):
        called["research"] = True
        return "x"

    monkeypatch.setattr(shows, "_research", _fail_research)

    out = shows.gather_shows("Austin, TX", [])

    assert out.shows == []
    assert called["research"] is False  # no LLM work when there's nothing to gather


# --- date validator: only canonical ISO survives ------------------------------


def test_show_date_keeps_iso_and_drops_freeform():
    base = dict(artist="A", venue="V", source_url="http://s")
    assert Show(date="2026-08-28", **base).date == "2026-08-28"
    assert Show(date="Friday, August 28", **base).date is None
    assert Show(date=None, **base).date is None


# --- _load_venues: curated-list loader ----------------------------------------


def test_load_venues_reads_venuelist_dump(tmp_path):
    p = tmp_path / "venues.json"
    p.write_text(
        VenueList(
            region="Chicago, IL",
            venues=[Venue(name="Metro", city="Chicago", source_url="https://x")],
        ).model_dump_json()
    )
    loaded = shows._load_venues(str(p))
    assert [v.name for v in loaded] == ["Metro"]


def test_load_venues_reads_bare_list(tmp_path):
    p = tmp_path / "venues.json"
    p.write_text('[{"name": "Metro", "city": "Chicago", "source_url": "https://x"}]')
    loaded = shows._load_venues(str(p))
    assert loaded[0].city == "Chicago"
