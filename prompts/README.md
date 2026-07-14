# Daily run prompts

The daily run picks its prompt in this order (first non-empty file wins):

1. `prompts/<YYYY-MM-DD>.md` — dated prompt for that specific day's run.
   **"Today" is evaluated in `PROMPT_TZ` (IANA name, default `UTC`)** — set it
   in `.env` to your local timezone if you want dated files to match your
   calendar day. The cron fires at 06:00 UTC.
2. `prompts/queue/*.md` — undated prompts, consumed oldest-first by filename.
   After the run that used one **succeeds**, the file is moved to
   `prompts/used/` (archived on the machine that ran it — never deleted,
   never reused). A failed run does not consume the prompt.
3. `prompts/default.md` — fallback; a run never fails for lack of a prompt.

Every run logs which prompt file it used.

## File format

Markdown. The body is the editorial brief handed to the research agent.
Optional YAML frontmatter sets the article's category (keep these to a small,
stable set — it's written to the draft's frontmatter / sent to your backend):

```markdown
---
category: Security
---
Investigate the most consequential supply-chain security incident reported
this month and what defenders should change because of it.
```

If `category` is omitted, the site falls back to "Research".

## Workflow

Drop a file in here (dated, queued, or edit `default.md`) and run the agent.
If you schedule the run on another machine (e.g. a cron job that pulls this
repo first), a prompt committed before the run is picked up that day.

`prompts/used/` is gitignored — the archive lives on the machine that
consumed the prompt.
