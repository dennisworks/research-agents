# Research Agents — Technical Brief

A technical description of how the research-agent pipeline works. For usage and
configuration see the top-level [`README.md`](../README.md); for the
contributor workflow see [`CLAUDE.md`](../CLAUDE.md).

## What it is

A small, deliberately un-frameworked research pipeline: **a topic goes in, a
cited Markdown article comes out.** One search agent, a two-stage LLM flow,
Pydantic-validated output. It runs as a CLI/cron job (there is no server), and
it's written to be read and forked rather than configured.

```
brief → [research: ReAct agent + Tavily] → notes → [write: structured-output LLM] → Article → sink
```

## The two-stage pipeline (`research_agents/agent.py`)

The core is `run(brief, current_article=None)`, which chains two stages against
a **single shared model** (`RESEARCH_MODEL`, default
`anthropic:claude-opus-4-8`):

1. **Research** — `research_topic()` builds a ReAct agent via LangChain's
   `create_agent(llm, [TavilySearch(max_results=5)], system_prompt=RESEARCH_PROMPT)`.
   The agent is instructed to run several distinct searches across different
   angles, then emit research notes: findings, concrete figures, points of
   disagreement, and a Sources list of URLs it actually used. Tavily does the
   crawling on its own infrastructure — the agent only needs outbound HTTPS to
   `api.tavily.com` and `api.anthropic.com`.

2. **Write** — `write_article()` calls the same model with
   `.with_structured_output(Article)` to turn the notes into a validated
   object. It's **retried once**, because the structured-output call
   occasionally returns an incomplete object (seen in production as Pydantic
   validation errors), and a failed run means no article that day.

Claude's message content can be a string or a list of content blocks, so
`_text_of()` normalizes both before passing notes downstream.

## Output contract (`research_agents/schemas.py`)

The `Article` Pydantic model is the single source of truth for output shape —
validated the same whether written to disk or POSTed to a backend:

- `title`, `slug` (kebab-case), `summary` (1–2 sentences for feed previews)
- `body` — 500–900 words of Markdown, `##` headings, inline `[n]` citations
- `sources: list[Source]` (`title` + `url`), in citation order
- `tags` — 3–6 lowercase topical tags

## Model abstraction (`research_agents/config.py`)

`RESEARCH_MODEL` is a provider-prefixed spec passed straight to LangChain's
`init_chat_model`, so any provider it supports works — Anthropic (default),
OpenAI, Google Gemini, Ollama, or any **OpenAI-compatible** endpoint
(Groq/Together/OpenRouter/vLLM) via `RESEARCH_BASE_URL` + `RESEARCH_API_KEY`
(gated to the openai provider so it can't silently hit the wrong host).

The model must support two capabilities: **tool calling** (research) and
**structured output** (writing). `main.py --check-model` (`probe_model()`)
makes two small live calls and reports PASS/FAIL for each before a real run
depends on it. `RESEARCH_STRUCTURED_METHOD` can force `json_schema` /
`json_mode` / `function_calling` when a model rejects the default.

**Prompt caching:** when the provider is Anthropic (and
`RESEARCH_PROMPT_CACHE≠0`), an ephemeral `cache_control` breakpoint rides on
every request via `model_kwargs`. Across the multi-turn research loop, each
step re-reads the cached system prompt and prior tool results at ~0.1× input
cost. Gated on the provider, since only Anthropic accepts the field.

## Where the work comes from (prompt resolution)

With no `--topic`, `main.py` resolves a brief in priority order:

1. **Backend queue** (if `PUBLISH_URL`/`PUBLISH_TOKEN` set) —
   `remote_prompts.fetch(today)` asks the backend for today's prompt; any error
   or 404 falls through silently (a backend outage must not stop the daily
   run).
2. **Local `prompts/` directory** (`prompts.py`) — dated
   `prompts/YYYY-MM-DD.md` → oldest file in `prompts/queue/` →
   `prompts/default.md`. "Today" is evaluated in `PROMPT_TZ` (default UTC).

Optional YAML frontmatter sets a `category`. **Queue prompts are one-shot** and
consumed two-phase: resolved at run start, confirmed only *after* a successful
publish (`archive()` moves the file to `prompts/used/`; the remote equivalent
is `consume(id)`). A failed run leaves the prompt queued.

## Where the output goes (`research_agents/sinks.py`)

`get_sink()` selects one of two sinks by whether a backend is configured:

- **FileSink (default, zero-config)** — writes `output/<slug>.md` with YAML
  frontmatter (title, slug, date, summary, category, tags, sources) + the
  Markdown body.
- **WebhookSink (opt-in)** — POSTs to `<PUBLISH_URL>/api/research/ingest` with
  `Authorization: Bearer <token>`. `2xx {"id":...}` on success; **`409` →
  `DuplicateDraft`**, treated as a skip, not an error. This is the contract the
  author's own site implements; the legacy `DWORKS_*` env names are still
  honored for backward compatibility.

## Revision flow

A prompt (local or remote) can carry a `revises` slug. `main.py` fetches the
current article via `sink.fetch_article(slug)` (WebhookSink hits
`/api/research/item`; FileSink returns `None` — revision is a backend-only
feature) and threads its content through both stages. The research agent then
focuses on *what changed* and re-verifies key claims; the writer produces a
complete self-contained replacement with renumbered citations.

## Operational surface

- **Entrypoints:** `--topic` (ad-hoc), no args (daily/queue), `--manual`
  (claim a backend "Run now" request), `--dry-run` (print JSON, no publish),
  `--check-model`.
- **Deployment:** built from the root `Dockerfile`, run from cron (06:00 UTC),
  needs only outbound HTTPS to Anthropic + Tavily (+ your `PUBLISH_URL` host).
  Also ships a hardened `.devcontainer` (secure-devcontainer template) for
  agent-safe local dev.
- **CI:** `main` is protected; PRs run `lint` (ruff) + `test` (pytest, fully
  offline — LLM/Tavily never called, webhook HTTP monkeypatched) as required
  checks, plus a non-blocking live `smoke` that runs the real pipeline via
  `--dry-run`.

## Design posture

Two required secrets (`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`); everything else
defaults. One model, two stages, one validated schema, pluggable sink. The
prompts are plain string constants at the top of `agent.py` — voice, length,
and citation style are edited there, not configured.
