import os

import httpx

from .schemas import Article


class DuplicateDraft(Exception):
    """The ingest route already has a recent draft with this slug (HTTP 409)."""


def post_draft(
    article: Article,
    topic: str,
    prompt: str | None = None,
    category: str | None = None,
) -> dict:
    base = os.environ["DWORKS_API_URL"].rstrip("/")
    token = os.environ["DWORKS_INGEST_TOKEN"]
    payload = {**article.model_dump(), "topic": topic}
    # Optional, additive feed fields — omitted entirely when unset so older
    # ingest deployments stay compatible.
    if prompt:
        payload["prompt"] = prompt
    if category:
        payload["category"] = category
    resp = httpx.post(
        f"{base}/api/research/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 409:
        raise DuplicateDraft(article.slug)
    resp.raise_for_status()
    return resp.json()
