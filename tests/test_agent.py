import pytest

from research_agents import agent


def _raise_import_error(*args, **kwargs):
    raise ImportError("Unable to import the provider package")


def test_known_provider_error_points_at_extra(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "openai:gpt-4.1")
    monkeypatch.setattr(agent, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        agent._make_llm()
    assert "uv sync --extra openai" in str(exc.value)


def test_unknown_provider_error_points_at_pip_package(monkeypatch):
    # google_vertexai has no extra defined; the hint should name the real
    # package, not misdirect to the `google` (google-genai) extra.
    monkeypatch.setenv("RESEARCH_MODEL", "google_vertexai:gemini-2.5-pro")
    monkeypatch.setattr(agent, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        agent._make_llm()
    msg = str(exc.value)
    assert "langchain-google-vertexai" in msg
    assert "--extra google" not in msg


def test_bare_model_name_error_suggests_prefix_not_bogus_extra(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "gpt-4o")
    monkeypatch.setattr(agent, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        agent._make_llm()
    msg = str(exc.value)
    assert "provider prefix" in msg
    assert "--extra" not in msg  # no nonsensical `--extra <phrase>` suggestion
