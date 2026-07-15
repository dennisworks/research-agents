from research_agents import config

_BACKEND_KEYS = ("PUBLISH_URL", "PUBLISH_TOKEN", "DWORKS_API_URL", "DWORKS_INGEST_TOKEN")


def _clear_backend(monkeypatch):
    for key in _BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_model_spec_defaults_to_provider_prefixed_anthropic(monkeypatch):
    monkeypatch.delenv("RESEARCH_MODEL", raising=False)
    assert config.model_spec() == config.DEFAULT_MODEL
    assert config.DEFAULT_MODEL.startswith("anthropic:")


def test_model_spec_override(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "openai:gpt-4.1")
    assert config.model_spec() == "openai:gpt-4.1"


def test_model_params_defaults(monkeypatch):
    for key in ("RESEARCH_MAX_TOKENS", "RESEARCH_TIMEOUT", "RESEARCH_TEMPERATURE"):
        monkeypatch.delenv(key, raising=False)
    params = config.model_params()
    assert params == {"max_tokens": 8000, "timeout": 300}
    # temperature omitted unless explicitly set (some models reject it)
    assert "temperature" not in params


def test_model_params_env_overrides(monkeypatch):
    monkeypatch.setenv("RESEARCH_MAX_TOKENS", "4096")
    monkeypatch.setenv("RESEARCH_TIMEOUT", "120")
    monkeypatch.setenv("RESEARCH_TEMPERATURE", "0.2")
    params = config.model_params()
    assert params == {"max_tokens": 4096, "timeout": 120, "temperature": 0.2}


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
