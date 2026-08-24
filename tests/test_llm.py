import pytest

from research_agents import llm
from research_agents.shows_schemas import ShowList, VenueList


def _raise_import_error(*args, **kwargs):
    raise ImportError("Unable to import the provider package")


def test_known_provider_error_points_at_extra(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "openai:gpt-4.1")
    monkeypatch.setattr(llm, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        llm.make_llm()
    assert "uv sync --extra openai" in str(exc.value)


def test_unknown_provider_error_points_at_pip_package(monkeypatch):
    # google_vertexai has no extra defined; the hint should name the real
    # package, not misdirect to the `google` (google-genai) extra.
    monkeypatch.setenv("RESEARCH_MODEL", "google_vertexai:gemini-2.5-pro")
    monkeypatch.setattr(llm, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        llm.make_llm()
    msg = str(exc.value)
    assert "langchain-google-vertexai" in msg
    assert "--extra google" not in msg


def test_bare_model_name_error_suggests_prefix_not_bogus_extra(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "gpt-4o")
    monkeypatch.setattr(llm, "init_chat_model", _raise_import_error)
    with pytest.raises(RuntimeError) as exc:
        llm.make_llm()
    msg = str(exc.value)
    assert "provider prefix" in msg
    assert "--extra" not in msg  # no nonsensical `--extra <phrase>` suggestion


def test_text_of_handles_string_and_blocks():
    assert llm.text_of("plain") == "plain"
    blocks = [
        {"type": "text", "text": "hello"},
        {"type": "tool_use", "name": "x"},  # non-text block ignored
        {"type": "text", "text": "world"},
    ]
    assert llm.text_of(blocks) == "hello\nworld"


def _a_validation_error():
    from pydantic import ValidationError

    try:
        VenueList(region=None, venues=[])  # region must be a str -> raises
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


class _ScriptedExtractor:
    """Yields each item from `results` per invoke; raises it if it's an exception."""

    def __init__(self, results):
        self._results = list(results)

    def invoke(self, messages):
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _ScriptedLLM:
    def __init__(self, extractor):
        self._extractor = extractor
        self.methods = []

    def with_structured_output(self, schema, **kwargs):
        self.methods.append(kwargs.get("method"))
        return self._extractor


def test_structured_invoke_retries_once_on_validation_error():
    ok = ShowList(region="X", shows=[])
    model = _ScriptedLLM(_ScriptedExtractor([_a_validation_error(), ok]))
    assert llm.structured_invoke(model, ShowList, [("user", "x")]) is ok


def test_structured_invoke_does_not_retry_transport_errors():
    model = _ScriptedLLM(
        _ScriptedExtractor([RuntimeError("network"), ShowList(region="X", shows=[])])
    )
    with pytest.raises(RuntimeError):
        llm.structured_invoke(model, ShowList, [("user", "x")])


def test_structured_invoke_passes_method_through():
    model = _ScriptedLLM(_ScriptedExtractor([ShowList(region="X", shows=[])]))
    llm.structured_invoke(model, ShowList, [("user", "x")], method="json_schema")
    assert model.methods == ["json_schema"]
