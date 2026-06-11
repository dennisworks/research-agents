"""Resolve which prompt drives a daily run.

Resolution order (first non-empty wins):
  1. prompts/<YYYY-MM-DD>.md   — dated file for "today" in PROMPT_TZ (default UTC)
  2. prompts/queue/*.md        — oldest first (lexicographic filename order)
  3. prompts/default.md        — always-present fallback

Prompt files are Markdown; an optional YAML frontmatter block may set
`category:` (a short, stable editorial label passed through to the feed).
Queue prompts are one-shot: after the run that consumed one succeeds, call
archive() to move it to prompts/used/ — never deleted, never reused. Dated
and default prompts are never moved.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class ResolvedPrompt:
    path: Path
    text: str
    category: str | None
    from_queue: bool


def _parse(path: Path) -> tuple[str, str | None]:
    raw = path.read_text()
    match = _FRONTMATTER.match(raw)
    category = None
    body = raw
    if match:
        meta, body = match.groups()
        for line in meta.splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() == "category":
                category = value.strip().strip("\"'") or None
    return body.strip(), category


def _load(path: Path, from_queue: bool) -> ResolvedPrompt | None:
    if not path.is_file():
        return None
    text, category = _parse(path)
    if not text:
        return None  # empty prompt — fall through to the next tier
    return ResolvedPrompt(path=path, text=text, category=category, from_queue=from_queue)


def resolve(prompts_dir: Path) -> ResolvedPrompt:
    tz = ZoneInfo(os.environ.get("PROMPT_TZ", "UTC"))
    today = datetime.now(tz).date().isoformat()

    if resolved := _load(prompts_dir / f"{today}.md", from_queue=False):
        return resolved

    for queued in sorted((prompts_dir / "queue").glob("*.md")):
        if resolved := _load(queued, from_queue=True):
            return resolved

    if resolved := _load(prompts_dir / "default.md", from_queue=False):
        return resolved

    raise FileNotFoundError(
        f"no usable prompt in {prompts_dir} — prompts/default.md must exist and be non-empty"
    )


def archive(resolved: ResolvedPrompt) -> Path | None:
    """Move a consumed queue prompt to prompts/used/. No-op for dated/default."""
    if not resolved.from_queue:
        return None
    used = resolved.path.parent.parent / "used"
    used.mkdir(exist_ok=True)
    target = used / resolved.path.name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        target = used / f"{resolved.path.stem}-{stamp}{resolved.path.suffix}"
    resolved.path.rename(target)
    return target
