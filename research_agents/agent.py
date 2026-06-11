"""Two-stage pipeline per topic:

1. A ReAct agent (Claude + Tavily search) gathers research notes with sources.
2. A structured-output call turns the notes into an Article ready for ingest.
"""

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_tavily import TavilySearch

from .schemas import Article

MODEL = "claude-opus-4-8"

RESEARCH_PROMPT = """You are a meticulous research assistant. Use the search tool
to investigate the topic you are given. Run several distinct searches covering
different angles before concluding. Then write detailed research notes:
key findings, concrete facts and figures, points of disagreement between
sources, and a "Sources" section listing every URL you actually drew from
(title + URL). Only include claims supported by the search results."""

WRITER_PROMPT = """You are an editor turning research notes into a publishable
article. Write in clear, engaging prose for a general technical audience.
Do not invent facts or sources beyond what the notes contain. The body must
be Markdown with ## section headings and inline [n] citations matching the
sources list."""


def _make_llm() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL, max_tokens=8000, timeout=300)


def _text_of(content) -> str:
    # Claude message content can be a string or a list of content blocks.
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    )


def research_topic(brief: str) -> str:
    """Run the search agent against an editorial brief; return research notes."""
    search = TavilySearch(max_results=5)
    agent = create_agent(_make_llm(), [search], system_prompt=RESEARCH_PROMPT)
    result = agent.invoke(
        {"messages": [("user", f"Research the following editorial brief:\n\n{brief}")]}
    )
    return _text_of(result["messages"][-1].content)


def write_article(brief: str, notes: str) -> Article:
    """Turn research notes into a structured Article."""
    writer = _make_llm().with_structured_output(Article)
    return writer.invoke(
        [
            ("system", WRITER_PROMPT),
            ("user", f"Editorial brief: {brief}\n\nResearch notes:\n\n{notes}"),
        ]
    )


def run(brief: str) -> Article:
    notes = research_topic(brief)
    return write_article(brief, notes)
