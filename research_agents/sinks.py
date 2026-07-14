"""Where a finished Article goes.

Two sinks, selected by `get_sink()`:

- FileSink (default): write each draft as a Markdown file with YAML
  frontmatter under an output directory. No configuration, no network — this
  is what you get out of the box.
- WebhookSink (optional): POST the draft to an HTTP endpoint with a bearer
  token, e.g. a CMS or an editorial review queue. Enabled by setting
  PUBLISH_URL + PUBLISH_TOKEN (see config.publish_backend). It posts to
  `<PUBLISH_URL>/api/research/ingest`; the expected request/response contract
  is documented in the README under "Publishing to a backend".
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import yaml

from . import config
from .schemas import Article


class DuplicateDraft(Exception):
    """The backend already has a draft with this slug (HTTP 409)."""


class FileSink:
    """Write drafts to `output_dir/<slug>.md` as Markdown + YAML frontmatter."""

    def __init__(self, output_dir: str):
        self.dir = Path(output_dir)

    def fetch_article(self, slug: str) -> dict | None:
        # Revision-from-source is a backend feature; file output has no
        # canonical "current" article to build on.
        return None

    def publish(
        self,
        article: Article,
        *,
        topic: str,
        prompt: str | None = None,
        category: str | None = None,
        revises: str | None = None,
    ) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{article.slug}.md"
        meta = {
            "title": article.title,
            "slug": article.slug,
            "date": date.today().isoformat(),
            "summary": article.summary,
            "category": category,
            "tags": article.tags,
            "sources": [s.model_dump() for s in article.sources],
        }
        meta = {k: v for k, v in meta.items() if v is not None}
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
        path.write_text(f"---\n{front}\n---\n\n{article.body}\n")
        return str(path)


class WebhookSink:
    """POST drafts to an HTTP backend (bearer auth)."""

    def __init__(self, base_url: str, token: str):
        self.base = base_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def fetch_article(self, slug: str) -> dict | None:
        """Current content of an existing article (any status), or None when
        the slug is unknown. Used by revision runs; other HTTP errors raise so
        a revision never silently runs without its source article."""
        resp = httpx.get(
            f"{self.base}/api/research/item",
            params={"slug": slug},
            headers=self.headers,
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def publish(
        self,
        article: Article,
        *,
        topic: str,
        prompt: str | None = None,
        category: str | None = None,
        revises: str | None = None,
    ) -> str:
        payload = {**article.model_dump(), "topic": topic}
        # Optional, additive fields — omitted entirely when unset so older
        # backend deployments stay compatible.
        if prompt:
            payload["prompt"] = prompt
        if category:
            payload["category"] = category
        if revises:
            payload["revises"] = revises
        resp = httpx.post(
            f"{self.base}/api/research/ingest",
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        if resp.status_code == 409:
            raise DuplicateDraft(article.slug)
        resp.raise_for_status()
        return str(resp.json().get("id", "ok"))


def get_sink(output_dir: str) -> FileSink | WebhookSink:
    """WebhookSink when a publish backend is configured, else FileSink."""
    backend = config.publish_backend()
    if backend:
        return WebhookSink(*backend)
    return FileSink(output_dir)
