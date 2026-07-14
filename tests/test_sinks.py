import httpx
import pytest
import yaml

from research_agents.schemas import Article, Source
from research_agents.sinks import DuplicateDraft, FileSink, WebhookSink, get_sink

_BACKEND_KEYS = ("PUBLISH_URL", "PUBLISH_TOKEN", "DWORKS_API_URL", "DWORKS_INGEST_TOKEN")


def _article():
    return Article(
        title="WebGPU in 2026",
        slug="webgpu-2026",
        summary="A summary.",
        body="## Intro\nBody with a claim [1].",
        sources=[Source(title="Spec", url="https://ex.com")],
        tags=["webgpu", "graphics"],
    )


class _FakeResp:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


# --- FileSink -------------------------------------------------------------


def test_filesink_writes_valid_frontmatter_and_body(tmp_path):
    path = FileSink(str(tmp_path)).publish(_article(), topic="webgpu", category="Graphics")

    text = (tmp_path / "webgpu-2026.md").read_text()
    assert text.startswith("---\n")
    assert "## Intro" in text

    meta = yaml.safe_load(text.split("---\n")[1])
    assert meta["title"] == "WebGPU in 2026"
    assert meta["slug"] == "webgpu-2026"
    assert meta["category"] == "Graphics"
    assert meta["sources"][0]["url"] == "https://ex.com"
    assert path.endswith("webgpu-2026.md")


def test_filesink_omits_unset_category(tmp_path):
    FileSink(str(tmp_path)).publish(_article(), topic="webgpu")
    meta = yaml.safe_load((tmp_path / "webgpu-2026.md").read_text().split("---\n")[1])
    assert "category" not in meta


def test_filesink_cannot_fetch_source_article(tmp_path):
    assert FileSink(str(tmp_path)).fetch_article("anything") is None


# --- get_sink selection ---------------------------------------------------


def test_get_sink_defaults_to_file(tmp_path, monkeypatch):
    for key in _BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert isinstance(get_sink(str(tmp_path)), FileSink)


def test_get_sink_uses_webhook_when_backend_set(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISH_URL", "http://backend")
    monkeypatch.setenv("PUBLISH_TOKEN", "tok")
    assert isinstance(get_sink(str(tmp_path)), WebhookSink)


def test_get_sink_honors_legacy_backend_env(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLISH_URL", raising=False)
    monkeypatch.delenv("PUBLISH_TOKEN", raising=False)
    monkeypatch.setenv("DWORKS_API_URL", "http://backend")
    monkeypatch.setenv("DWORKS_INGEST_TOKEN", "tok")
    assert isinstance(get_sink(str(tmp_path)), WebhookSink)


# --- WebhookSink ----------------------------------------------------------


def test_webhook_publish_posts_expected_payload(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers)
        return _FakeResp(200, {"id": "abc"})

    monkeypatch.setattr(httpx, "post", fake_post)

    ref = WebhookSink("http://backend", "tok").publish(
        _article(), topic="webgpu", prompt="brief", category="Graphics"
    )

    assert ref == "abc"
    assert captured["url"] == "http://backend/api/research/ingest"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"]["slug"] == "webgpu-2026"
    assert captured["json"]["topic"] == "webgpu"
    assert captured["json"]["prompt"] == "brief"
    assert captured["json"]["category"] == "Graphics"


def test_webhook_publish_omits_unset_optional_fields(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return _FakeResp(200, {"id": "x"})

    monkeypatch.setattr(httpx, "post", fake_post)
    WebhookSink("http://backend", "tok").publish(_article(), topic="webgpu")

    for optional in ("prompt", "category", "revises"):
        assert optional not in captured["json"]


def test_webhook_publish_raises_on_409(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp(409))
    with pytest.raises(DuplicateDraft):
        WebhookSink("http://backend", "tok").publish(_article(), topic="webgpu")


def test_webhook_fetch_article_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(404))
    assert WebhookSink("http://backend", "tok").fetch_article("nope") is None


def test_webhook_fetch_article_returns_json(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(200, {"title": "T", "sources": []}))
    assert WebhookSink("http://backend", "tok").fetch_article("slug")["title"] == "T"
