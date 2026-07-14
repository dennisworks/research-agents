# research-agents — working notes

A small LangChain + Tavily research-agent pipeline (topic in → cited Markdown
article out). See `README.md` for what it does and how to run it. This file is
the contributor/agent workflow.

## Pull request workflow

`main` is protected — never push to it directly. All changes reach `main` via a
merged PR. Develop on a `dev`/feature branch, open a PR to `main`, and before
merging:

1. **CI is green** — the required checks `lint` (ruff) and `test` (pytest) pass.
2. **Review threads resolved** — address every Copilot review comment (apply the
   fix or reply) and resolve the thread. Merges are blocked on unresolved
   conversations.
3. **Glance at the live smoke** — the `smoke (live, non-blocking)` check runs the
   real Claude + Tavily pipeline via `--dry-run`. It's informational, not
   required: a green means the shipping model still produces a valid article; a
   red is usually a transient network/model blip, so check the log before
   worrying. It never blocks the merge.

Everything above runs automatically on each push to the PR branch. The only
manual step is the final review-and-merge.

## Testing

Add or update tests in `tests/` whenever you change behavior. They're
deterministic and offline — the LLM and Tavily are never called; `WebhookSink`'s
HTTP calls are monkeypatched. Run them with:

```
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Coverage lives in: `test_config.py` (env resolution + legacy `DWORKS_*`
fallback), `test_sinks.py` (file frontmatter, sink selection, webhook payload +
409), `test_prompts.py` (dated→queue→default resolution, frontmatter, archive),
`test_schemas.py` (`Article` validation).

## No staging server

This is a CLI/cron job, not a web app, so there's no staging deploy to preview.
"Exercise the change" means running the pipeline on the branch:

- `uv run python main.py --topic "..." --dry-run` — real run, prints JSON, no publish.
- `uv run python main.py --topic "..." --output-dir examples` — writes a Markdown
  file (uses the file sink; make sure no `PUBLISH_URL`/`DWORKS_*` is set in your
  environment if you don't want it POSTing to a backend).

CI's `smoke` job does the `--dry-run` form automatically on every PR.
