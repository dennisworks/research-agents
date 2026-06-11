"""Prompt queue hosted in dworks (entered via /admin/research/prompts).

The daily run asks dworks for a prompt first; the local prompts/ directory
(see prompts.py) is the offline fallback. Consumption is two-phase here too:
resolve at run start, confirm via consume() only after the run succeeds.
"""

import os
import sys
from dataclasses import dataclass

import httpx


@dataclass
class RemotePrompt:
    id: str
    text: str
    category: str | None


def _client_config() -> tuple[str, dict]:
    base = os.environ["DWORKS_API_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['DWORKS_INGEST_TOKEN']}"}
    return base, headers


def fetch(date: str) -> RemotePrompt | None:
    """The prompt dworks has queued for `date`, or None (incl. on any error —
    a dworks outage must not stop the daily run)."""
    try:
        base, headers = _client_config()
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
        return RemotePrompt(id=data["id"], text=data["text"], category=data.get("category"))
    except Exception as e:
        print(f"[prompt] dworks queue unreachable ({e}); using local prompts", file=sys.stderr)
        return None


def claim_manual() -> RemotePrompt | None:
    """Claim the pending "Run now" request, or None (incl. on any error).
    Claiming clears the request flag server-side, so a failed run is not
    retried by the poller; the prompt stays queued until consume()."""
    try:
        base, headers = _client_config()
        resp = httpx.post(
            f"{base}/api/research/prompt/manual",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return RemotePrompt(id=data["id"], text=data["text"], category=data.get("category"))
    except Exception as e:
        print(f"[prompt] manual claim failed ({e})", file=sys.stderr)
        return None


def consume(prompt_id: str) -> None:
    """Mark a remote prompt used. Best-effort: a failure here means the prompt
    may run twice, which is preferable to crashing after a successful run."""
    try:
        base, headers = _client_config()
        httpx.post(
            f"{base}/api/research/prompt/consume",
            json={"id": prompt_id},
            headers=headers,
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        print(f"[prompt] WARN: consume failed for {prompt_id}: {e}", file=sys.stderr)
