from pydantic import BaseModel, Field


class Source(BaseModel):
    title: str
    url: str


class Article(BaseModel):
    """A finished draft. This is the shape written to disk (as frontmatter)
    or POSTed to a publish backend — see research_agents/sinks.py."""

    title: str
    slug: str = Field(description="URL-safe kebab-case slug derived from the title")
    summary: str = Field(description="One or two sentences for feed/preview display")
    body: str = Field(
        description=(
            "The full article in Markdown, 500-900 words, with ## section "
            "headings. Cite claims inline as [n] matching the sources list."
        )
    )
    sources: list[Source] = Field(description="Every source actually used, in citation order")
    tags: list[str] = Field(description="3-6 lowercase topical tags")
