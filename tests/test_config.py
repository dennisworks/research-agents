from research_agents import config

_BACKEND_KEYS = ("PUBLISH_URL", "PUBLISH_TOKEN", "DWORKS_API_URL", "DWORKS_INGEST_TOKEN")


def _clear_backend(monkeypatch):
    for key in _BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_model_defaults(monkeypatch):
    monkeypatch.delenv("RESEARCH_MODEL", raising=False)
    assert config.model() == config.DEFAULT_MODEL


def test_model_override(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "claude-sonnet-4-6")
    assert config.model() == "claude-sonnet-4-6"


def test_publish_backend_none_when_unset(monkeypatch):
    _clear_backend(monkeypatch)
    assert config.publish_backend() is None


def test_publish_backend_new_names_and_strips_slash(monkeypatch):
    _clear_backend(monkeypatch)
    monkeypatch.setenv("PUBLISH_URL", "https://cms.example.com/")
    monkeypatch.setenv("PUBLISH_TOKEN", "tok")
    assert config.publish_backend() == ("https://cms.example.com", "tok")


def test_publish_backend_honors_legacy_names(monkeypatch):
    _clear_backend(monkeypatch)
    monkeypatch.setenv("DWORKS_API_URL", "http://vps:3000")
    monkeypatch.setenv("DWORKS_INGEST_TOKEN", "legacy")
    assert config.publish_backend() == ("http://vps:3000", "legacy")


def test_publish_backend_needs_both_url_and_token(monkeypatch):
    _clear_backend(monkeypatch)
    monkeypatch.setenv("PUBLISH_URL", "https://cms.example.com")
    assert config.publish_backend() is None
