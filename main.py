"""Run the research agent.

    python main.py                 # daily mode: resolve prompt (dated -> queue -> default)
    python main.py --topic "..."   # ad-hoc topic, ignores the prompts directory
    python main.py --dry-run       # print article JSON to stdout, don't publish
    python main.py --manual        # backend only: run the prompt behind a "Run now" request

By default a finished draft is written to ./output/<slug>.md. Set
PUBLISH_URL + PUBLISH_TOKEN to POST it to an HTTP backend instead (see the
README). Daily mode logs which prompt it used; a consumed queue prompt is
archived (or backend-consumed) only after the run succeeds.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from research_agents import config, remote_prompts
from research_agents.agent import run
from research_agents.prompts import ResolvedPrompt, archive, resolve
from research_agents.sinks import DuplicateDraft, get_sink


def _topic_label(text: str) -> str:
    """Short human label for the article list, from the brief's first line."""
    first = text.strip().splitlines()[0]
    return first[:80]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", help="ad-hoc topic; skips prompt resolution")
    parser.add_argument(
        "--manual",
        action="store_true",
        help='backend only: run the prompt behind a pending "Run now" request',
    )
    parser.add_argument("--prompts-dir", default="prompts")
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("OUTPUT_DIR", config.DEFAULT_OUTPUT_DIR),
        help="where file-sink drafts are written (ignored when a backend is set)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print JSON instead of publishing")
    args = parser.parse_args()

    sink = get_sink(args.output_dir)
    has_backend = config.publish_backend() is not None

    resolved: ResolvedPrompt | None = None
    remote: remote_prompts.RemotePrompt | None = None
    if args.topic:
        brief, category = args.topic, None
        print("[prompt] ad-hoc --topic", file=sys.stderr)
    elif args.manual:
        # A manual "Run now" request is a backend feature; there is no local
        # equivalent to fall back to.
        if not has_backend:
            print(
                "[manual] --manual needs a publish backend (PUBLISH_URL/PUBLISH_TOKEN)",
                file=sys.stderr,
            )
            return 2
        remote = remote_prompts.claim_manual()
        if remote is None:
            print("[manual] no pending run request", file=sys.stderr)
            return 0
        brief, category = remote.text, remote.category
        print(f"[prompt] manual run {remote.id} (category={category or '-'})", file=sys.stderr)
    else:
        # A configured backend's queue wins; the local prompts/ directory is
        # the fallback (and the only source when there's no backend).
        tz = ZoneInfo(os.environ.get("PROMPT_TZ", "UTC"))
        today = datetime.now(tz).date().isoformat()
        remote = remote_prompts.fetch(today) if has_backend else None
        if remote:
            brief, category = remote.text, remote.category
            print(
                f"[prompt] remote queue {remote.id} (category={category or '-'})", file=sys.stderr
            )
        else:
            resolved = resolve(Path(args.prompts_dir))
            brief, category = resolved.text, resolved.category
            print(
                f"[prompt] {resolved.path} (category={category or '-'}, queued={resolved.from_queue})",
                file=sys.stderr,
            )

    # A revision prompt names an existing article; fetch its current content
    # so the agent builds on it instead of starting cold. Failing here leaves
    # the prompt queued (consume only happens after a successful run).
    current_article: str | None = None
    revises = remote.revises if remote else None
    if revises:
        try:
            item = sink.fetch_article(revises)
        except Exception as e:
            print(f"[error] could not fetch article {revises}: {e}", file=sys.stderr)
            return 1
        if item is None:
            print(f"[error] revises slug not found: {revises}", file=sys.stderr)
            return 1
        source_lines = "\n".join(
            f"{i + 1}. {s['title']} — {s['url']}" for i, s in enumerate(item.get("sources") or [])
        )
        current_article = f"# {item['title']}\n\n{item['summary']}\n\n{item['body']}" + (
            f"\n\nSources:\n{source_lines}" if source_lines else ""
        )
        print(f"[revise] fetched current article for {revises}", file=sys.stderr)

    try:
        article = run(brief, current_article)
    except Exception as e:
        print(f"[error] research run failed: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(article.model_dump_json(indent=2))
        return 0

    try:
        ref = sink.publish(
            article,
            topic=_topic_label(brief),
            prompt=brief,
            category=category,
            revises=revises,
        )
        print(f"[published] {article.slug} -> {ref}", file=sys.stderr)
    except DuplicateDraft:
        print(f"[skipped] duplicate slug: {article.slug}", file=sys.stderr)
    except Exception as e:
        print(f"[error] publish failed for {article.slug}: {e}", file=sys.stderr)
        return 1

    # Only a successful (or duplicate-skipped) run consumes a queued prompt.
    if remote:
        remote_prompts.consume(remote.id)
        print(f"[prompt] consumed remote prompt {remote.id}", file=sys.stderr)
    elif resolved and resolved.from_queue:
        archived_to = archive(resolved)
        print(f"[prompt] archived {resolved.path.name} -> {archived_to}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
