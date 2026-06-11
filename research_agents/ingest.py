import os

import httpx

from .schemas import Article


class DuplicateDraft(Exception):
    """The ingest route already has a recent draft with this slug (HTTP 409)."""


def _client_config() -> tuple[str, dict]:
    base = os.environ["DWORKS_API_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['DWORKS_INGEST_TOKEN']}"}
    return base, headers


def fetch_article(slug: str) -> dict | None:
    """Current content of an existing article (any status), or None when the
    slug is unknown. Used by revision runs; other HTTP errors raise so a
    revision never silently runs without its source article."""
    base, headers = _client_config()
    resp = httpx.get(
        f"{base}/api/research/item",
        params={"slug": slug},
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def post_draft(
    article: Article,
    topic: str,
    prompt: str | None = None,
    category: str | None = None,
    revises: str | None = None,
) -> dict:
    base, headers = _client_config()
    payload = {**article.model_dump(), "topic": topic}
    # Optional, additive feed fields — omitted entirely when unset so older
    # ingest deployments stay compatible.
    if prompt:
        payload["prompt"] = prompt
    if category:
        payload["category"] = category
    if revises:
        payload["revises"] = revises
    resp = httpx.post(
        f"{base}/api/research/ingest",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 409:
        raise DuplicateDraft(article.slug)
    resp.raise_for_status()
    return resp.json()
