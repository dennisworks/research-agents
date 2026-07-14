import pytest
from pydantic import ValidationError

from research_agents.schemas import Article, Source


def _article():
    return Article(
        title="T",
        slug="t",
        summary="s",
        body="## H\nbody [1]",
        sources=[Source(title="Spec", url="https://ex.com")],
        tags=["a", "b"],
    )


def test_article_roundtrips():
    a = _article()
    dumped = a.model_dump()
    assert dumped["slug"] == "t"
    assert dumped["sources"][0] == {"title": "Spec", "url": "https://ex.com"}


def test_article_requires_all_fields():
    with pytest.raises(ValidationError):
        Article(title="only a title")
