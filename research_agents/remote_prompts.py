"""Optional prompt queue hosted by the publish backend.

When a backend is configured (PUBLISH_URL + PUBLISH_TOKEN), the daily run can
ask it for a prompt first, falling back to the local prompts/ directory (see
prompts.py). Consumption is two-phase: resolve at run start, confirm via
consume() only after the run succeeds. With no backend configured every
function here is a no-op, so a file-only setup just uses local prompts.

This targets the same endpoints as the dworks reference backend
(`/api/research/prompt`, `.../prompt/manual`, `.../prompt/consume`); a backend
that doesn't implement them simply 404s and the run falls back.
"""

import sys
from dataclasses import dataclass

import httpx

from . import config


@dataclass
class RemotePrompt:
    id: str
    text: str
    category: str | None
    # Slug of an existing article this prompt revises; the run fetches the
    # current content and the resulting draft replaces it on publish.
    revises: str | None = None


def _client_config() -> tuple[str, dict] | None:
    backend = config.publish_backend()
    if backend is None:
        return None
    base, token = backend
    return base, {"Authorization": f"Bearer {token}"}


def fetch(date: str) -> RemotePrompt | None:
    """The prompt the backend has queued for `date`, or None (incl. on any
    error — a backend outage must not stop the daily run)."""
    cfg = _client_config()
    if cfg is None:
        return None
    try:
        base, headers = cfg
        resp = httpx.get(
            f"{base}/api/research/prompt",
            params={"date": date},
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return RemotePrompt(
            id=data["id"],
            text=data["text"],
            category=data.get("category"),
            revises=data.get("revises"),
        )
    except Exception as e:
        print(f"[prompt] remote queue unreachable ({e}); using local prompts", file=sys.stderr)
        return None


def claim_manual() -> RemotePrompt | None:
    """Claim the pending "Run now" request, or None (incl. on any error).
    Claiming clears the request flag server-side, so a failed run is not
    retried by the poller; the prompt stays queued until consume()."""
    cfg = _client_config()
    if cfg is None:
        return None
    try:
        base, headers = cfg
        resp = httpx.post(
            f"{base}/api/research/prompt/manual",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return RemotePrompt(
            id=data["id"],
            text=data["text"],
            category=data.get("category"),
            revises=data.get("revises"),
        )
    except Exception as e:
        print(f"[prompt] manual claim failed ({e})", file=sys.stderr)
        return None


def consume(prompt_id: str) -> None:
    """Mark a remote prompt used. Best-effort: a failure here means the prompt
    may run twice, which is preferable to crashing after a successful run."""
    cfg = _client_config()
    if cfg is None:
        return None
    try:
        base, headers = cfg
        httpx.post(
            f"{base}/api/research/prompt/consume",
            json={"id": prompt_id},
            headers=headers,
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        print(f"[prompt] WARN: consume failed for {prompt_id}: {e}", file=sys.stderr)
