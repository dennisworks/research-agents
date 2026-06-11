"""Run the research agent.

    python main.py                 # daily mode: resolve prompt (dated -> queue -> default)
    python main.py --topic "..."   # ad-hoc topic, ignores the prompts directory
    python main.py --dry-run       # print article JSON to stdout, no ingest

Daily mode logs which prompt file it used; a consumed queue prompt is
archived to prompts/used/ only after the run succeeds.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from research_agents.agent import run
from research_agents.ingest import DuplicateDraft, post_draft
from research_agents.prompts import ResolvedPrompt, archive, resolve


def _topic_label(text: str) -> str:
    """Short human label for the admin list, from the brief's first line."""
    first = text.strip().splitlines()[0]
    return first[:80]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", help="ad-hoc topic; skips prompt resolution")
    parser.add_argument("--prompts-dir", default="prompts")
    parser.add_argument("--dry-run", action="store_true", help="print JSON instead of posting to dworks")
    args = parser.parse_args()

    resolved: ResolvedPrompt | None = None
    if args.topic:
        brief, category = args.topic, None
        print(f"[prompt] ad-hoc --topic", file=sys.stderr)
    else:
        resolved = resolve(Path(args.prompts_dir))
        brief, category = resolved.text, resolved.category
        print(
            f"[prompt] {resolved.path} (category={category or '-'}, queued={resolved.from_queue})",
            file=sys.stderr,
        )

    try:
        article = run(brief)
    except Exception as e:
        print(f"[error] research run failed: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(article.model_dump_json(indent=2))
        return 0

    try:
        result = post_draft(article, topic=_topic_label(brief), prompt=brief, category=category)
        print(f"[ingested] {article.slug} -> {result.get('id', 'ok')}", file=sys.stderr)
    except DuplicateDraft:
        print(f"[skipped] duplicate slug: {article.slug}", file=sys.stderr)
    except Exception as e:
        print(f"[error] ingest failed for {article.slug}: {e}", file=sys.stderr)
        return 1

    # Only a successful (or duplicate-skipped) run consumes a queue prompt.
    if resolved and resolved.from_queue:
        archived_to = archive(resolved)
        print(f"[prompt] archived {resolved.path.name} -> {archived_to}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
