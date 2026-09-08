# How-to writer prompts

A second persona directory for how-to / step-by-step guides. Mount it over
`/app/prompts` the same way as `prompts/`:

```
docker run --rm --env-file .env \
  -v "$(pwd)/prompts-howto:/app/prompts" \
  research-agents --prompts-dir prompts
```

This persona is normally driven by an explicit **`--brief-file`** (a full brief
pasted through the control plane), which skips prompt resolution entirely. The
files here are the fallback for a plain scheduled/daily run:

- `default.md` — always-present fallback brief (category `How-to`).
- `queue/*.md` — optional one-shot briefs, consumed oldest-first.

Same file format as [`../prompts/README.md`](../prompts/README.md): Markdown
body with optional `category:` frontmatter. Voice/length/citation style are
global (set in `research_agents/agent.py`), not per-directory.
