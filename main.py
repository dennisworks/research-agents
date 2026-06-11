"""Run the research agent.

    python main.py                 # daily mode: resolve prompt (dated -> queue -> default)
    python main.py --manual        # run the prompt behind a pending "Run now" request, if any
    python main.py --topic "..."   # ad-hoc topic, ignores the prompts directory
    python main.py --dry-run       # print article JSON to stdout, no ingest

Daily mode logs which prompt file it used; a consumed queue prompt is
archived to prompts/used/ only after the run succeeds.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from research_agents import remote_prompts
from research_agents.agent import run
from research_agents.ingest import DuplicateDraft, fetch_article, post_draft
from research_agents.prompts import ResolvedPrompt, archive, resolve


def _topic_label(text: str) -> str:
    """Short human label for the admin list, from the brief's first line."""
    first = text.strip().splitlines()[0]
    return first[:80]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", help="ad-hoc topic; skips prompt resolution")
    parser.add_argument(
        "--manual",
        action="store_true",
        help='run the prompt behind a pending "Run now" request; exits quietly if none',
    )
    parser.add_argument("--prompts-dir", default="prompts")
    parser.add_argument("--dry-run", action="store_true", help="print JSON instead of posting to dworks")
    args = parser.parse_args()

    resolved: ResolvedPrompt | None = None
    remote: remote_prompts.RemotePrompt | None = None
    if args.topic:
        brief, category = args.topic, None
        print(f"[prompt] ad-hoc --topic", file=sys.stderr)
    elif args.manual:
        # No local fallback here: a manual run only makes sense for the
        # specific prompt that was requested.
        remote = remote_prompts.claim_manual()
        if remote is None:
            print("[manual] no pending run request", file=sys.stderr)
            return 0
        brief, category = remote.text, remote.category
        print(
            f"[prompt] manual run {remote.id} (category={category or '-'})",
            file=sys.stderr,
        )
    else:
        # The dworks queue (entered at /admin/research/prompts) wins;
        # the local prompts/ directory is the offline fallback.
        tz = ZoneInfo(os.environ.get("PROMPT_TZ", "UTC"))
        today = datetime.now(tz).date().isoformat()
        remote = remote_prompts.fetch(today)
        if remote:
            brief, category = remote.text, remote.category
            print(
                f"[prompt] dworks queue {remote.id} (category={category or '-'})",
                file=sys.stderr,
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
            item = fetch_article(revises)
        except Exception as e:
            print(f"[error] could not fetch article {revises}: {e}", file=sys.stderr)
            return 1
        if item is None:
            print(f"[error] revises slug not found in dworks: {revises}", file=sys.stderr)
            return 1
        source_lines = "\n".join(
            f"{i + 1}. {s['title']} — {s['url']}"
            for i, s in enumerate(item.get("sources") or [])
        )
        current_article = (
            f"# {item['title']}\n\n{item['summary']}\n\n{item['body']}"
            + (f"\n\nSources:\n{source_lines}" if source_lines else "")
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
        result = post_draft(
            article,
            topic=_topic_label(brief),
            prompt=brief,
            category=category,
            revises=revises,
        )
        print(f"[ingested] {article.slug} -> {result.get('id', 'ok')}", file=sys.stderr)
    except DuplicateDraft:
        print(f"[skipped] duplicate slug: {article.slug}", file=sys.stderr)
    except Exception as e:
        print(f"[error] ingest failed for {article.slug}: {e}", file=sys.stderr)
        return 1

    # Only a successful (or duplicate-skipped) run consumes a queued prompt.
    if remote:
        remote_prompts.consume(remote.id)
        print(f"[prompt] consumed dworks prompt {remote.id}", file=sys.stderr)
    elif resolved and resolved.from_queue:
        archived_to = archive(resolved)
        print(f"[prompt] archived {resolved.path.name} -> {archived_to}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
