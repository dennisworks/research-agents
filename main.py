"""Run the research agents.

    python main.py                 # all topics from topics.yaml, post to dworks
    python main.py --topic "..."   # one ad-hoc topic
    python main.py --dry-run       # print article JSON to stdout, no ingest
"""

import argparse
import sys

import yaml
from dotenv import load_dotenv

from research_agents.agent import run
from research_agents.ingest import DuplicateDraft, post_draft


def load_topics(path: str) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)["topics"]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", help="run a single ad-hoc topic instead of topics.yaml")
    parser.add_argument("--topics-file", default="topics.yaml")
    parser.add_argument("--dry-run", action="store_true", help="print JSON instead of posting to dworks")
    args = parser.parse_args()

    if args.topic:
        topics = [{"name": args.topic}]
    else:
        topics = load_topics(args.topics_file)

    failures = 0
    for t in topics:
        name, focus = t["name"], t.get("focus")
        print(f"[research] {name}", file=sys.stderr)
        try:
            article = run(name, focus)
        except Exception as e:
            print(f"[error] {name}: {e}", file=sys.stderr)
            failures += 1
            continue

        if args.dry_run:
            print(article.model_dump_json(indent=2))
            continue

        try:
            result = post_draft(article, topic=name)
            print(f"[ingested] {article.slug} -> {result.get('id', 'ok')}", file=sys.stderr)
        except DuplicateDraft:
            print(f"[skipped] duplicate slug: {article.slug}", file=sys.stderr)
        except Exception as e:
            print(f"[error] ingest failed for {article.slug}: {e}", file=sys.stderr)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
