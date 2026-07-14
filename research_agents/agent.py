"""Two-stage pipeline per topic:

1. A ReAct agent (the configured chat model + Tavily search) gathers research notes.
2. A structured-output call turns the notes into a publishable Article.
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_tavily import TavilySearch

from . import config
from .schemas import Article

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


def _make_llm() -> BaseChatModel:
    spec = config.model_spec()
    try:
        return init_chat_model(spec, **config.model_params())
    except ImportError as e:
        # init_chat_model imports the provider package lazily; turn the raw
        # ModuleNotFound into an actionable "install this extra" message.
        provider = spec.split(":", 1)[0] if ":" in spec else "the selected provider"
        extra = config.PROVIDER_EXTRAS.get(provider, provider)
        raise RuntimeError(
            f"The provider package for '{spec}' isn't installed. "
            f"Install it with `uv sync --extra {extra}` "
            f"(or `pip install 'research-agents[{extra}]'`)."
        ) from e


def _text_of(content) -> str:
    # Claude message content can be a string or a list of content blocks.
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def research_topic(brief: str, current_article: str | None = None) -> str:
    """Run the search agent against an editorial brief; return research notes."""
    search = TavilySearch(max_results=5)
    agent = create_agent(_make_llm(), [search], system_prompt=RESEARCH_PROMPT)
    request = f"Research the following editorial brief:\n\n{brief}"
    if current_article:
        request = (
            "An existing published article is being revised. Here is its "
            f"current content:\n\n{current_article}\n\n---\n\n"
            "Research the following revision brief. Focus on what is new, "
            "changed, or missing relative to the current article; also verify "
            "its key claims still hold.\n\n"
            f"{brief}"
        )
    result = agent.invoke({"messages": [("user", request)]})
    return _text_of(result["messages"][-1].content)


def write_article(brief: str, notes: str, current_article: str | None = None) -> Article:
    """Turn research notes into a structured Article.

    Retried once: the structured-output call occasionally returns an
    incomplete object (seen in production as Pydantic validation errors),
    and a failed daily run means no article that day.
    """
    writer = _make_llm().with_structured_output(Article)
    request = f"Editorial brief: {brief}\n\nResearch notes:\n\n{notes}"
    if current_article:
        request = (
            "You are revising an existing article. Produce a complete, "
            "self-contained replacement: keep the content that is still "
            "accurate, and rework it per the brief and the new research "
            "notes. Renumber citations to match the final sources list "
            "(carry over sources from the current article that you still "
            "rely on).\n\n"
            f"Current article:\n\n{current_article}\n\n---\n\n{request}"
        )
    messages = [
        ("system", WRITER_PROMPT),
        ("user", request),
    ]
    try:
        return writer.invoke(messages)
    except Exception:
        return writer.invoke(messages)


def run(brief: str, current_article: str | None = None) -> Article:
    notes = research_topic(brief, current_article)
    return write_article(brief, notes, current_article)
