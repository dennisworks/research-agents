# research-agents

A small, readable research-agent pipeline. Give it a topic; it searches the
web and writes a cited Markdown article.

```
topic / brief
  → ReAct agent (LLM + Tavily search) gathers notes with sources
  → structured-output pass writes an Article (title, summary, body, tags, sources)
  → output/<slug>.md            (or POST to your own backend)
```

It's deliberately minimal — one search agent, a two-stage LLM pipeline,
Pydantic-validated output — meant to be read and forked, not configured like a
framework.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/dennisworks/research-agents
cd research-agents
uv sync
cp .env.example .env        # then add ANTHROPIC_API_KEY and TAVILY_API_KEY

uv run python main.py --topic "the state of WebGPU in 2026"
```

That writes `output/<slug>.md` — Markdown with YAML frontmatter (title,
summary, category, tags, sources). Add `--dry-run` to print the raw JSON
instead of writing a file. See [`examples/`](examples/) for a full generated
article.

- `ANTHROPIC_API_KEY` — console.anthropic.com
- `TAVILY_API_KEY` — app.tavily.com (free tier: 1,000 credits/month)

## How it works

`research_agents/agent.py` runs two stages against one brief:

1. **Research** — a ReAct agent (`create_agent` + `TavilySearch`) runs several
   searches and writes notes with a Sources list. Tavily does the crawling on
   its own infrastructure; the agent only needs outbound HTTPS.
2. **Write** — a second call to the same model with `.with_structured_output(Article)`
   turns those notes into a validated `Article`. It's retried once, because the
   structured-output call occasionally returns an incomplete object.

Both stages share one model (`RESEARCH_MODEL`, default
`anthropic:claude-opus-4-8`). The system prompts are plain constants at the top
of `agent.py` — edit them to change voice, length, or citation style.

## Using a different model

`RESEARCH_MODEL` is a provider-prefixed spec passed to LangChain's
`init_chat_model`, so any provider it supports works — just install the matching
extra and set that provider's key:

| Provider | `RESEARCH_MODEL` | Install | Key env var |
| --- | --- | --- | --- |
| Anthropic (default) | `anthropic:claude-opus-4-8` | included | `ANTHROPIC_API_KEY` |
| OpenAI | `openai:gpt-4.1` | `uv sync --extra openai` | `OPENAI_API_KEY` |
| Google Gemini | `google_genai:gemini-2.5-pro` | `uv sync --extra google` | `GOOGLE_API_KEY` |
| Ollama (local) | `ollama:llama3.1` | `uv sync --extra ollama` | — |

The model must support **tool calling** (for the search step) and **structured
output** (for the article) — the major hosted models do; smaller local models
vary. Verify a model before relying on it with
`uv run python main.py --check-model`, which makes two small calls and reports
whether each capability works. Tune generation with `RESEARCH_MAX_TOKENS`,
`RESEARCH_TIMEOUT`, and `RESEARCH_TEMPERATURE`.

### OpenAI-compatible endpoints

Point the `openai` provider at any OpenAI-compatible host (Groq, Together,
OpenRouter, Fireworks, a local vLLM / LM Studio server) with `RESEARCH_BASE_URL`,
and pass that host's key via `RESEARCH_API_KEY` so you don't have to overwrite
`OPENAI_API_KEY`:

```
RESEARCH_MODEL=openai:llama-3.3-70b-versatile
RESEARCH_BASE_URL=https://api.groq.com/openai/v1
RESEARCH_API_KEY=gsk_…
```

If a model rejects the default structured-output mechanism, force one with
`RESEARCH_STRUCTURED_METHOD` (`json_schema`, `json_mode`, or `function_calling`).

## Prompts (unattended runs)

Run `main.py` with no `--topic` and it resolves a brief from the `prompts/`
directory: a dated file `prompts/YYYY-MM-DD.md`, then the oldest file in
`prompts/queue/`, then `prompts/default.md`. Queue files are one-shot (archived
to `prompts/used/` after a successful run). Frontmatter can set a `category`.
See `prompts/README.md` for the full rules.

## Publishing to a backend

By default drafts are written to disk. To POST each finished draft to your own
HTTP endpoint instead (a CMS, a review queue, a static-site pipeline), set:

```
PUBLISH_URL=https://your-backend.example.com
PUBLISH_TOKEN=your-bearer-token
```

With those set, the run POSTs to `<PUBLISH_URL>/api/research/ingest` with
`Authorization: Bearer <token>` and a JSON body:

```jsonc
{
  "title": "...", "slug": "...", "summary": "...",
  "body": "## markdown...", "tags": ["..."],
  "sources": [{ "title": "...", "url": "..." }],
  "topic": "short label",       // from the brief's first line
  "category": "AI Agents",      // optional, from prompt frontmatter
  "prompt": "the full brief",   // optional
  "revises": "existing-slug"    // optional, revision runs only
}
```

Expected responses: any `2xx` with `{"id": "..."}` on success; `409` if a
draft with that slug already exists (skipped, not treated as an error). Two
further optional endpoints enable a backend-hosted prompt queue and on-demand
runs — see `research_agents/remote_prompts.py` and `scripts/manual-poll.sh`.
This is the contract the author's own site implements; point your backend at
it, or ignore it and use the file output.

## Running on a schedule

Build the image with the root `Dockerfile` and run it from cron:

```
docker run --rm --env-file .env \
  -v "$(pwd)/output:/app/output" \
  research-agents --topic "..."     # or no --topic to use prompts/
```

The container needs outbound HTTPS to `api.anthropic.com` and `api.tavily.com`
(plus your `PUBLISH_URL` host, if set).

## License

MIT — see [LICENSE](LICENSE).

---

# Dev container (from secure-devcontainer template)


A hardened [Dev Container](https://containers.dev) template for running
[Claude Code](https://claude.com/claude-code) (or any AI coding agent) in
no-permissions / auto-accept mode with a meaningfully reduced blast radius if
the agent goes off the rails.

## Security model

| Control | Mechanism | Where |
| --- | --- | --- |
| Non-root agent user | Runs as `node` (uid 1000), no sudo | `devcontainer.json` `remoteUser` |
| No privilege escalation | `no-new-privileges:true` | `docker-compose.yml` `security_opt` |
| No Linux capabilities | `cap_drop: [ALL]` — agent inherits none | `docker-compose.yml` |
| Bounded filesystem | Only the host project is mounted; sibling repos and parent-dir secrets are not visible | `volumes: ..:/workspaces:cached` |
| Egress allowlist | iptables + ipset default-deny; programmed by root at PID 1, then NET_ADMIN is gone from the agent's user namespace | `init-firewall.sh` |
| Pinned CLI | `DISABLE_AUTOUPDATER=1` so Claude Code can't silently self-update inside the sandbox | `Dockerfile` |
| Persistent Claude login | Named volume `claude-config` survives rebuilds | `docker-compose.yml` |

The firewall runs once at container start as root (PID 1, which holds
`NET_ADMIN`) and then idles. The agent runs as `node`, which has neither
`NET_ADMIN` nor sudo, so it cannot tear the rules down. VS Code attaches over
Docker's exec channel, not over the network, so a locked-down firewall never
prevents attaching.

## Use as a template

```sh
# Create a new project from this template
gh repo create my-project --template dennisworks/secure-devcontainer --private --clone
cd my-project

# Open in VS Code and reopen in the dev container
code .
# Cmd+Shift+P → "Dev Containers: Reopen in Container"
```

Or copy the folder into an existing project:

```sh
cp -r /path/to/secure-devcontainer/.devcontainer ./
```

## Per-project customization

Most projects need to tweak a handful of things — every spot is commented in
the source files.

1. **Allowed egress** — `.devcontainer/init-firewall.sh`, `ALLOWED_DOMAINS`.
   The base set covers Claude + GitHub + npm. Uncomment / add entries for your
   language's package mirror (PyPI, crates.io, proxy.golang.org, …) and any
   API hosts your project calls.
2. **Post-create install** — `.devcontainer/devcontainer.json`,
   `postCreateCommand`. Append your project's install step:
   - Node: `"npm install && npm install -g @anthropic-ai/claude-code"`
   - Python: `"pip install -r requirements.txt && npm install -g @anthropic-ai/claude-code"`
3. **Auto-start dev server** — `.devcontainer/devcontainer.json`,
   `postStartCommand`. Uncomment and point at your run command.
4. **Sibling services** — `.devcontainer/docker-compose.yml`. Add `postgres`,
   `mongo`, `redis`, etc. as additional services and reference them via
   `depends_on`. Sibling services on the compose network are reachable without
   adding them to the firewall allowlist (the Docker subnet is already
   allowed).
5. **Ports** — `.devcontainer/docker-compose.yml`, `ports:` block. Uncomment
   to expose your dev server to the host.

## Verifying the sandbox

After the container boots:

```sh
# Inside the dev container, as `node`
sudo -n true 2>&1                 # should: "sudo: a password is required" (no sudo)
id                                # uid=1000(node) gid=1000(node)
curl -m 3 https://example.com     # should: time out (not on allowlist)
curl -m 5 https://api.github.com  # should: 200 OK (on allowlist)
iptables -L 2>&1                  # should: "Permission denied" (no NET_ADMIN)
```

## Notes

- `updateRemoteUserUID: false` skips the dev container startup uid remap (its
  chown can't run under `cap_drop: ALL`). On macOS Docker Desktop the file-
  sharing layer usually exposes bind-mount files as owned by the container's
  `node` user, so writes from the agent work fine. On Linux (and sometimes
  macOS under specific Docker Desktop settings), files appear at the host uid
  and `node` may hit EACCES on writes — see the next bullet.
- `init-firewall.sh` allowlists the IPs each domain resolves to **at startup**.
  CDN-backed hosts can rotate IPs; if a normally-allowed host starts failing,
  rebuild the container (or re-run the script as root) to re-resolve.
- Claude Code's auto-updater is disabled in the sandbox via
  `DISABLE_AUTOUPDATER=1` so the pinned version inside the container can't
  drift mid-session.

## Gotchas (and what to uncomment when you hit them)

All of these are documented inline in `.devcontainer/docker-compose.yml`; this
section is a map to find the right comment block.

- **`EACCES` on `npm install` / `pip install` writing into the workspace.**
  Your bind-mount uid mapping isn't showing files as `node`-owned. Two
  options:
  - Move write-heavy generated dirs (`node_modules`, `.next`, `.venv`,
    `target`) into named volumes — see the commented `workspaces-node-modules`
    example. Cleanest, and also avoids wrong-platform binaries from a host
    install contaminating the container.
  - For the `package.json` / lockfiles you must write through the bind mount,
    uncomment the `group_add: ["${HOST_GID:-20}"]` block and `chmod g+w` the
    affected files on the host.
- **`su: cannot set groups: Operation not permitted`** when you extend the
  entrypoint with `su node -c '...'` to drop privileges before launching a
  dev server. Uncomment the `- SETGID` / `- SETUID` lines in `cap_add` —
  those caps are needed for `su` to call `setgroups()`/`setuid()` even from
  root under `cap_drop: ALL`. They're held by PID 1 only and don't leak to
  the agent.
- **Sibling-project secrets leaking into the container.** Don't change
  `..:/workspaces:cached` to `../..:/workspaces` or similar — the whole
  point of the `..` mount is that it's exactly the workspace root. If you
  need files outside it, mount them in explicitly with `:ro`.

## License

MIT.
