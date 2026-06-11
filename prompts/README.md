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
stable set — they drive filtering on dennisworks.com):

```markdown
---
category: Security
---
Investigate the most consequential supply-chain security incident reported
this month and what defenders should change because of it.
```

If `category` is omitted, the site falls back to "Research".

## Owner workflow

Write a file, commit, push. The VPS cron pulls this repo before each daily
run, so a prompt pushed before 06:00 UTC is picked up that morning.

`prompts/used/` is gitignored — the archive lives on the machine that
consumed the prompt (the VPS for cron runs).
