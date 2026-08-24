from research_agents import agent


class _FakeWriter:
    def invoke(self, messages):
        from research_agents.schemas import Article

        return Article(title="t", slug="t", summary="s", body="b", sources=[], tags=["x"])


class _FakeLLM:
    def __init__(self, calls):
        self._calls = calls

    def with_structured_output(self, schema, **kwargs):
        self._calls.append(kwargs)
        return _FakeWriter()


def test_structured_method_passed_through_when_set(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "make_llm", lambda: _FakeLLM(calls))
    monkeypatch.setenv("RESEARCH_STRUCTURED_METHOD", "json_schema")
    agent.write_article("brief", "notes")
    assert calls == [{"method": "json_schema"}]


def test_structured_method_omitted_when_unset(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "make_llm", lambda: _FakeLLM(calls))
    monkeypatch.delenv("RESEARCH_STRUCTURED_METHOD", raising=False)
    agent.write_article("brief", "notes")
    assert calls == [{}]


class _Invokable:
    def __init__(self, result):
        self._result = result

    def invoke(self, _prompt):
        return self._result


class _ToolMsg:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _ProbeLLM:
    def __init__(self, tool_response, struct_result):
        self._tool_response = tool_response
        self._struct_result = struct_result

    def bind_tools(self, tools):
        return _Invokable(self._tool_response)

    def with_structured_output(self, schema, **kwargs):
        return _Invokable(self._struct_result)


def test_probe_model_all_capabilities_pass(monkeypatch):
    good = _ProbeLLM(
        tool_response=_ToolMsg([{"name": "_probe_tool", "args": {"value": "ping"}}]),
        struct_result=agent._ProbeSchema(ok=True, label="probe"),
    )
    monkeypatch.setattr(agent, "make_llm", lambda: good)
    res = agent.probe_model()
    assert res["tool_calling"][0] is True
    assert res["structured_output"][0] is True


def test_probe_model_reports_capability_failures(monkeypatch):
    bad = _ProbeLLM(tool_response=_ToolMsg([]), struct_result="not-a-schema-instance")
    monkeypatch.setattr(agent, "make_llm", lambda: bad)
    res = agent.probe_model()
    assert res["tool_calling"][0] is False  # no tool calls
    assert res["structured_output"][0] is False  # wrong result type
