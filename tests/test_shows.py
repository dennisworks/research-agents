from research_agents import shows
from research_agents.shows_schemas import ShowList, Venue, VenueList


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
